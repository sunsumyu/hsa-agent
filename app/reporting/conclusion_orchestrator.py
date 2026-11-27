"""
app/reporting/conclusion_orchestrator.py
==========================================
[SPEC-227 / Matt Pocock Deep Module] 审计结论仲裁与分流深模块 (Audit Conclusion Orchestrator)
"""

from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional, Tuple
from loguru import logger
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings


_RICH_SUMMARY_KEYWORDS = ("审计指标", "取证结果", "统计结果", "核查结果", "##")
_ZERO_FINDING_TEMPLATE = (
    "本次核查对底层物理数据表进行了全量扫描排查。在当前严格的审计特征与条件过滤下，"
    "未发现任何违规异常单据（违规记录数 0 条，涉及金额 ¥0.00），各项指标均处于客观合规基线范围内。"
)


def _detect_restricted_mode(
    state: Mapping[str, Any],
    raw_data_list: List[Dict[str, Any]],
    max_retries: int,
) -> bool:
    error_log = str(state.get("error_log") or "")
    sql_query = state.get("sql_query")
    retry_count = int(state.get("retry_count") or 0)
    sql_validated = bool(state.get("sql_validated", False))
    if bool(sql_query) and (bool(raw_data_list) or sql_validated):
        return False
    if (
        retry_count >= max_retries
        or "降级报告模式" in error_log
        or "REACHED_MAX_RETRIES" in error_log
        or not sql_validated
    ):
        logger.warning("🚨 [ConclusionOrchestrator] 检测到执行受限/逃生舱触发，开启受限核查模式。")
        return True
    return False


def _extract_coder_summary(state: Mapping[str, Any], sql_query: Any) -> Tuple[bool, str]:
    messages = state.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    last_content = str(getattr(last_ai, "content", "") or "").strip()
    is_rich = (
        bool(sql_query)
        and len(last_content) >= 50
        and not getattr(last_ai, "tool_calls", None)
        and any(k in last_content for k in _RICH_SUMMARY_KEYWORDS)
    )
    return is_rich, last_content


async def _generate_llm_conclusion(
    state: Mapping[str, Any],
    metadata: Dict[str, Any],
    hard_count: int,
    hard_sum: float,
    is_restricted: bool,
    config: Optional[RunnableConfig],
) -> str:
    from app.core.llm_provider import llm_provider
    from app.reporting.report_renderer import report_renderer

    semantic_align = metadata.get("semantic_alignment") or {}
    prompt_text = report_renderer.prepare_conclusion_prompt(
        metadata.get("user_question") or "医保专项审计",
        state.get("methodology", "基础核查逻辑"),
        state.get("execution_trace") or [],
        hard_count,
        hard_sum,
        rewritten_question=semantic_align.get("rewritten_question"),
        is_restricted=is_restricted,
        retrieved_citations=state.get("retrieved_citations"),
    )
    try:
        response = await llm_provider.chat(
            role="reporter",
            messages=[HumanMessage(content=prompt_text)],
            config=config,
            state=state,
            max_tokens=400,
        )
        return str(response.content).strip()
    except Exception as exc:
        logger.error(f"❌ [ConclusionOrchestrator] 结论生成失败: {exc}")
        if is_restricted:
            return "本次核查由于逻辑受限未产出确切违规结论。"
        return f"本次核查扫描 {hard_count} 条记录，涉及金额 ¥{hard_sum:,.2f}。"


async def resolve_conclusion(
    state: Mapping[str, Any],
    raw_data_list: List[Dict[str, Any]],
    hard_count: int,
    hard_sum: float,
    config: Optional[RunnableConfig] = None,
    max_retries: Optional[int] = None,
) -> Tuple[str, bool]:
    """仲裁并生成审计结论。"""
    resolved_retries = min(getattr(settings, "max_agent_retries", 1), 1) if max_retries is None else max_retries
    is_restricted = _detect_restricted_mode(state, raw_data_list, resolved_retries)

    metadata = dict(state.get("metadata") or {})
    user_question = metadata.get("user_question") or "医保专项审计"
    fast_route_id = metadata.get("fast_route_id")
    if fast_route_id:
        from app.reporting.fast_route_conclusion import generate_fast_route_conclusion

        return generate_fast_route_conclusion(raw_data_list, hard_sum, hard_count, user_question), is_restricted

    sql_query = state.get("sql_query")
    has_rich_summary, last_content = _extract_coder_summary(state, sql_query)
    if has_rich_summary:
        logger.info("✨ [ConclusionOrchestrator] 检测到 Coder 已输出完整高质量审计结论，直接采纳，跳过独立 Reporter LLM 调用")
        return last_content, is_restricted

    if bool(sql_query) and hard_count == 0 and not is_restricted:
        logger.info("✨ [ConclusionOrchestrator] 零违规合规基线审计直通，使用确定性合规模板，跳过独立 Reporter LLM 调用")
        return _ZERO_FINDING_TEMPLATE, is_restricted

    if is_restricted and not raw_data_list:
        error_log = str(state.get("error_log") or "")
        fallback_msg = (
            f"本次核查由于执行逻辑受限未产出确切违规结论。{error_log[:150]}"
            if error_log else "本次核查由于执行受限未产出确切违规结论。"
        )
        return fallback_msg, True

    conclusion = await _generate_llm_conclusion(state, metadata, hard_count, hard_sum, is_restricted, config)
    return conclusion, is_restricted
