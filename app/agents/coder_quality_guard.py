"""
app/agents/coder_quality_guard.py
=================================
[Matt Pocock Deep Module] Coder 执行前语义门控审查与执行后反思自愈评估深模块。

职责内聚：
1. 工具调用前置语义合规审查 (check_pre_execution_gate)
2. 工具执行后多维质量门控：SQL Linter + 数值一致性 (run_quality_linter)
3. 执行结果闭环反思自愈评估 (check_post_execution_gate)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from loguru import logger


@dataclass(frozen=True)
class PreExecutionGateResult:
    passed: bool
    error: Optional[str] = None
    sql_arg: str = ""


@dataclass(frozen=True)
class PostExecutionGateResult:
    passed: bool
    error_feedback: Optional[str] = None


def check_pre_execution_gate(
    tool_calls: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> PreExecutionGateResult:
    """
    [Gate 2] SQL 物理执行前的语义拦截审查
    """
    for tc in (tool_calls or []):
        if tc.get("name") == "execute_audit_sql":
            sql_arg = tc.get("args", {}).get("sql", "")
            if sql_arg:
                from app.core.context.gates import QualityGate
                validation_res = QualityGate.validate_sql_semantics(state, sql_arg)
                if not validation_res.get("passed", True):
                    gate_error = validation_res.get("error") or "SQL 语义审查校验失败"
                    return PreExecutionGateResult(
                        passed=False,
                        error=gate_error,
                        sql_arg=sql_arg,
                    )
                return PreExecutionGateResult(
                    passed=True,
                    error=None,
                    sql_arg=sql_arg,
                )
    return PreExecutionGateResult(passed=True, error=None, sql_arg="")


def run_quality_linter(
    sql: str,
    methodology: Optional[str] = None,
    raw_data: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    运行 SQL 语法 Linter 与数据数值异常检测
    """
    if not sql:
        return None

    # 1. SQL Linter 语法/方言逻辑审查
    from app.skills.sql_validator import sql_validator
    is_ok, linter_msg = sql_validator.agentic_linter(sql)
    if not is_ok:
        return f"【SQL 逻辑审查拦截】{linter_msg}"

    # 2. 数值异常与一致性检测
    from app.core.booster import booster
    rows = booster.parse_table_to_rows(raw_data)
    anomaly_msg = booster.detect_anomalous_consistency(rows)
    if anomaly_msg:
        return f"【数值异常拦截】{anomaly_msg}"

    return None


def check_post_execution_gate(
    sql: Optional[str],
    methodology: Optional[str],
    raw_data: Optional[List[Dict[str, Any]]],
    intent: Optional[Any] = None,
) -> PostExecutionGateResult:
    """
    [Quality Gate + Reflexion] 综合执行结果门控审查与闭环自愈判定
    """
    if not sql:
        return PostExecutionGateResult(passed=True, error_feedback=None)

    # 1. 运行底层质量门控 (Linter & Booster)
    gate_error = run_quality_linter(sql=sql, methodology=methodology, raw_data=raw_data)

    # 2. [Reflexion 闭环自愈] 后验反思评估 (Evaluator-Optimizer)
    from app.core.reflection.audit_reflection_engine import AuditReflectionEngine
    row_count = len(raw_data or [])
    refl_res = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=row_count,
        intent=intent,
        error_msg=gate_error,
    )

    if refl_res.needs_retry:
        refl_feedback = refl_res.diagnostic_feedback or gate_error or "执行结果异常，触发自愈"
        return PostExecutionGateResult(passed=False, error_feedback=refl_feedback)

    if gate_error:
        return PostExecutionGateResult(passed=False, error_feedback=gate_error)

    return PostExecutionGateResult(passed=True, error_feedback=None)
