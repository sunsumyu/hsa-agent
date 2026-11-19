from typing import Dict, Any, Optional
from loguru import logger
from app.core.intent_validator import intent_validator
from app.core.query_classifier import query_classifier
from app.core.guardrails.guardrail_result import GuardrailResult
from app.core.guardrails.diagnostic_interpreter import DiagnosticInterpreter


def guard_intent_alignment(state: Dict[str, Any]) -> GuardrailResult:
    """[V178.10 / SPEC-227 / Matt Pocock Deep Module] 
    Gate 1: 意图与方法论的一致性校验守卫。

    隐藏实现细节：
    - 提问类型动态感知 (RANKING, AGGREGATION, THRESHOLD_FILTER)
    - 阈值决策上下文提取与绑定
    - 意图反偏离对齐校验
    - 专家级诊断建议生成与标准化契约封装
    - 异常防御性降级放行

    Args:
        state: 包含 original_question, methodology, query_type 等字段的审计状态
        
    Returns:
        GuardrailResult(passed=bool, error=str or None, warnings=[], diagnostic_hint=str or None)
    """
    try:
        original_question = state.get("original_question", "")
        methodology = state.get("methodology", "")
        
        if not original_question or not methodology:
            # 缺少必要信息时默认放行，避免阻塞流水线
            return GuardrailResult(passed=True, error=None, warnings=[], diagnostic_hint=None)
        
        # 分类查询类型
        query_type = query_classifier.classify(original_question)
        
        # 获取阈值决策信息
        threshold_decision = state.get("threshold_decision", {})
        
        # 执行对齐校验
        result = intent_validator.validate_alignment(
            original_query=original_question,
            query_type=query_type,
            methodology=methodology,
            threshold_decision=threshold_decision,
        )
        
        passed = result.get("passed", True)
        errors = result.get("errors", [])
        error_msg = "; ".join(errors) if errors else None
        
        if not passed:
            logger.warning(f"[Gate 1] Intent validation failed: {error_msg}")
        
        hint = DiagnosticInterpreter.interpret_gate1_intent(error_msg, [])
        return GuardrailResult(passed=passed, error=error_msg, warnings=[], diagnostic_hint=hint)
        
    except Exception as e:
        # 校验异常时默认放行，避免阻塞流水线
        logger.warning(f"[Gate 1] Intent validation error (defaulting to pass): {e}")
        return GuardrailResult(passed=True, error=None, warnings=[], diagnostic_hint=None)
