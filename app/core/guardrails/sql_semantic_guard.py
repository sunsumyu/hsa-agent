import re
from typing import Any, List, Optional
from loguru import logger
from app.core.registry.archetype_registry import archetype_registry, ArchetypeCategory
from app.core.sql_evidence_resolver import resolve_user_query
from app.core.guardrails.contradiction_detector import ContradictionDetector
from app.core.guardrails.guardrail_result import GuardrailResult
from app.core.guardrails.diagnostic_interpreter import DiagnosticInterpreter

_BASELINE_SQL_KEYWORDS = ("QUANTILE", "PERCENTILE", "AVG(", "MEDIAN(", "STDDEV(")
_SCALAR_AGG_FUNCTIONS = ("COUNT(", "COUNT (", "SUM(", "SUM (", "AVG(", "AVG (")
_SCHEMA_PROBE_PATTERN = re.compile(
    r'^\s*SELECT\s+(\*|[\w\s,]+)\s+FROM\s+\w+\s+LIMIT\s+[1-5]\s*;?\s*$',
    re.IGNORECASE,
)


def _extract_guard_question(state: Any) -> str:
    """安全提取规范化后的用户原始审计问题。"""
    try:
        return resolve_user_query(
            state=state if isinstance(state, dict) else None,
            fallback_keys=["user_input", "original_question", "user_query", "question"],
        ) or ""
    except Exception as exc:
        logger.debug(f"[Gate 2] Resolve user query skipped: {exc}")
        return ""


def _check_ranking_baseline_warning(
    sql_upper: str,
    question_lower: str,
    matched_archetypes: List[Any],
) -> Optional[GuardrailResult]:
    """检测排名类问题是否意外引入全局基线统计，返回非阻断告警结果。"""
    is_ranking_query = any(arch.category == ArchetypeCategory.RANKING for arch in matched_archetypes)
    if not is_ranking_query:
        is_ranking_query = any(kw in question_lower for kw in ["排名", "最高", "前", "top"])
    has_baseline = any(kw in sql_upper for kw in _BASELINE_SQL_KEYWORDS)
    if not (is_ranking_query and has_baseline and "OVER" not in sql_upper and "GROUP BY" not in sql_upper):
        return None

    warning = "RANKING查询包含基线计算步骤(quantile/avg)，可能产生语义偏离"
    logger.warning(f"[Gate 2] {warning}")
    hint = DiagnosticInterpreter.interpret_gate2_sql(None, [warning], matched_archetypes)
    return GuardrailResult(passed=True, error=None, warnings=[warning], diagnostic_hint=hint)


def _check_archetype_raw_limit(
    sql: str,
    sql_upper: str,
    matched_archetypes: List[Any],
    warnings: List[str],
) -> Optional[GuardrailResult]:
    """校验全量统计原型是否违规对明细流水施加 LIMIT 采样。"""
    has_group_by = "GROUP BY" in sql_upper
    has_limit = "LIMIT " in sql_upper or "LIMIT\n" in sql_upper or "LIMIT\t" in sql_upper
    is_scalar_agg = any(fn in sql_upper for fn in _SCALAR_AGG_FUNCTIONS)
    is_pure_schema_probe = bool(_SCHEMA_PROBE_PATTERN.match(sql)) and "WHERE" not in sql_upper

    for arch in matched_archetypes:
        if arch.forbid_raw_limit and has_limit and not has_group_by and not is_scalar_agg and not is_pure_schema_probe:
            err_msg = arch.enforcement_hint or f"本任务为【{arch.display_name}】任务，必须使用 GROUP BY 进行全量统计，严禁对明细流水施加 LIMIT 采样！"
            hint = DiagnosticInterpreter.interpret_gate2_sql(err_msg, warnings, matched_archetypes)
            return GuardrailResult(passed=False, error=err_msg, warnings=warnings, diagnostic_hint=hint)
    return None


def guard_sql_semantics(state: Any, sql: str) -> GuardrailResult:
    """[V178.10 / SPEC-227 / Matt Pocock Deep Module]
    SQL 语义与领域任务原型不变式守卫。
    """
    if not sql:
        hint = DiagnosticInterpreter.interpret_gate2_sql("SQL为空", [])
        return GuardrailResult(passed=False, error="SQL为空", warnings=[], diagnostic_hint=hint)

    warnings: List[str] = []
    sql_upper = sql.upper().strip()
    question_lower = _extract_guard_question(state).lower()
    matched_archetypes = archetype_registry.match_archetypes(question_lower)

    ranking_result = _check_ranking_baseline_warning(sql_upper, question_lower, matched_archetypes)
    if ranking_result is not None:
        return ranking_result

    limit_result = _check_archetype_raw_limit(sql, sql_upper, matched_archetypes, warnings)
    if limit_result is not None:
        return limit_result

    violation = ContradictionDetector.detect(sql, archetypes=matched_archetypes)
    if violation:
        err_msg = f"【静态语义恒假拦截】{violation.message} 冲突谓词: {violation.conflicting_predicates}"
        logger.warning(f"[Gate 2 Contradiction] {err_msg}")
        hint = DiagnosticInterpreter.interpret_gate2_sql(err_msg, warnings, matched_archetypes)
        return GuardrailResult(passed=False, error=err_msg, warnings=warnings, diagnostic_hint=hint)

    hint = DiagnosticInterpreter.interpret_gate2_sql(None, warnings, matched_archetypes) if warnings else None
    return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=hint)
