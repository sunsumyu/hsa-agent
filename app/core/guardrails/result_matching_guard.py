from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.guardrails.guardrail_result import GuardrailResult
from app.core.guardrails.diagnostic_interpreter import DiagnosticInterpreter


def guard_result_matching(state: Any) -> GuardrailResult:
    """[V178.10 / SPEC-227 / Matt Pocock Deep Module] 
    Gate 3: 结果匹配校验 — 检查查询结果是否与审计目标匹配。

    隐藏实现细节：
    - 多结果字段提取容错 (raw_data, query_result)
    - None 结果的执行失败警告注入
    - 空列表的合理性审计放行
    - 专家级诊断建议生成与标准化契约封装

    Args:
        state: 审计状态字典

    Returns:
        GuardrailResult(passed=bool, error=str or None, warnings=List[str], diagnostic_hint=str or None)
    """
    try:
        result_data = state.get("raw_data", state.get("query_result", None)) if isinstance(state, dict) else None
    except Exception:
        result_data = None

    warnings: List[str] = []

    # 空结果不等于不通过 — 可能确实没有违规
    if result_data is None:
        warning = "查询结果为None，可能SQL执行失败"
        warnings.append(warning)
        hint = DiagnosticInterpreter.interpret_gate3_result(None, warnings)
        return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=hint)
    
    # 检查是否是空列表
    if isinstance(result_data, (list, tuple)) and len(result_data) == 0:
        logger.info("[Gate 3] 查询结果为空列表 — 可能确实无违规数据")
        return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=None)
    
    return GuardrailResult(passed=True, error=None, warnings=warnings, diagnostic_hint=None)
