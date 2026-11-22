import re
from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.registry.archetype_registry import archetype_registry, ArchetypeCategory
from app.core.sql_evidence_resolver import resolve_user_query
from app.core.guardrails.contradiction_detector import ContradictionDetector
from app.core.guardrails.guardrail_result import GuardrailResult
from app.core.guardrails.diagnostic_interpreter import DiagnosticInterpreter


def guard_sql_semantics(state: Any, sql: str) -> GuardrailResult:
    """[V178.10 / SPEC-227 / Matt Pocock Deep Module] 
    SQL 语义与领域任务原型不变式守卫。

    隐藏实现细节：
    - 多来源提问与任务原型自动匹配
    - RANKING 基线查询偏离检测与警告
    - 针对全量分析任务的明细流水 LIMIT 采样非法截断拦截
    - 纯物理表结构探查安全豁免
    - AST 静态恒假互斥谓词冲突判定
    - 专家级诊断建议生成与标准化契约封装

    Args:
        state: 审计状态字典或状态机对象
        sql: 待执行的 SQL 语句

    Returns:
        GuardrailResult(passed=bool, error=str or None, warnings=List[str], diagnostic_hint=str or None)
    """
    try:
        methodology = state.get("methodology", "") if isinstance(state, dict) else ""
        # [SPEC-227 SSOT] 优先通过 sql_evidence_resolver 深模块解析纯净用户意图
        original_question = resolve_user_query(
            state=state if isinstance(state, dict) else None,
            fallback_keys=["user_input", "original_question", "user_query", "question"]
        )
    except Exception:
        methodology = ""
        original_question = ""

    warnings: List[str] = []
    if not sql:
        hint = DiagnosticInterpreter.interpret_gate2_sql("SQL为空", [])
        return GuardrailResult(passed=False, error="SQL为空", warnings=[], diagnostic_hint=hint)

    sql_upper = sql.upper().strip()
    question_lower = (original_question or "").lower()
    
    # 领域任务原型解析 (基于 ArchetypeRegistry 单一事实源)
    matched_archetypes = archetype_registry.match_archetypes(question_lower)

    # 规则1: RANKING 原型查询 + 不必要的基线计算
    baseline_keywords = ["QUANTILE", "PERCENTILE", "AVG(", "MEDIAN(", "STDDEV("]
    is_ranking_query = any(arch.category == ArchetypeCategory.RANKING for arch in matched_archetypes)
    if not is_ranking_query:
        is_ranking_query = any(kw in question_lower for kw in ["排名", "最高", "前", "top"])
    has_baseline = any(kw in sql_upper for kw in baseline_keywords)
    
    if is_ranking_query and has_baseline and "OVER" not in sql_upper and "GROUP BY" not in sql_upper:
        warning = "RANKING查询包含基线计算步骤(quantile/avg)，可能产生语义偏离"
        warnings.append(warning)
        logger.warning(f"[Gate 2] {warning}")
        hint = DiagnosticInterpreter.interpret_gate2_sql(None, warnings, matched_archetypes)
        # 不拦截，只警告 — 某些排名查询确实需要基线
        return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=hint)

    # 规则2: [Task Archetype Guard] 领域任务原型不变式守卫 (基于 ArchetypeRegistry)
    has_group_by = "GROUP BY" in sql_upper
    has_limit = "LIMIT " in sql_upper or "LIMIT\n" in sql_upper or "LIMIT\t" in sql_upper
    # 标量聚合 (如 SELECT count(*), sum(...) FROM t) 本身即为全量计算，不属于对明细流水的抽样截断
    is_scalar_agg = any(fn in sql_upper for fn in ["COUNT(", "COUNT (", "SUM(", "SUM (", "AVG(", "AVG ("])

    # 探查豁免：仅用于观察物理表结构的小批量纯探查 (如 SELECT * FROM tbl LIMIT 5 无业务筛选)，放行探查
    is_pure_schema_probe = bool(re.match(r'^\s*SELECT\s+(\*|[\w\s,]+)\s+FROM\s+\w+\s+LIMIT\s+[1-5]\s*;?\s*$', sql, re.IGNORECASE)) and "WHERE" not in sql_upper

    for arch in matched_archetypes:
        if arch.forbid_raw_limit and has_limit and not has_group_by and not is_scalar_agg and not is_pure_schema_probe:
            err_msg = arch.enforcement_hint or f"本任务为【{arch.display_name}】任务，必须使用 GROUP BY 进行全量统计，严禁对明细流水施加 LIMIT 采样！"
            hint = DiagnosticInterpreter.interpret_gate2_sql(err_msg, warnings, matched_archetypes)
            return GuardrailResult(passed=False, error=err_msg, warnings=warnings, diagnostic_hint=hint)

    # 规则3: [Neuro-Symbolic Gate] 静态 AST 恒假互斥与领域任务原型不变式守卫 (Matt Pocock Deep Module)
    violation = ContradictionDetector.detect(sql, archetypes=matched_archetypes)
    if violation:
        err_msg = f"【静态语义恒假拦截】{violation.message} 冲突谓词: {violation.conflicting_predicates}"
        logger.warning(f"[Gate 2 Contradiction] {err_msg}")
        hint = DiagnosticInterpreter.interpret_gate2_sql(err_msg, warnings, matched_archetypes)
        return GuardrailResult(passed=False, error=err_msg, warnings=warnings, diagnostic_hint=hint)

    hint = DiagnosticInterpreter.interpret_gate2_sql(None, warnings, matched_archetypes) if warnings else None
    return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=hint)
