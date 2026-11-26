"""
app/agents/coder_inference_coordinator.py
=========================================
[Matt Pocock Deep Module & SSOT]
Coder 智能体推理与重试调度协同器 (CoderInferenceCoordinator)。
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from loguru import logger
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.core.llm_provider import llm_provider
from app.core.protocol.tool_normalizer import ToolResponseNormalizer
from app.core.sql_evidence_resolver import resolve_core_audit_sql


_MANDATE_RETRY_PROMPT = (
    "【强制执行指令】你尚未物理执行任何有效 SQL 审计查询！严禁仅以自然语言文本回复或反问用户。"
    "当前系统已连接真实的 ClickHouse 数据库，所有数据均在库中，请立即调用 `execute_audit_sql` "
    "工具执行对应的物理表查询获取真实统计数据！"
)


@dataclass
class CoderInferenceResult:
    """推理协同执行产物契约"""
    response: AIMessage
    has_tool_calls: bool
    direct_return_state: Optional[Dict[str, Any]] = None


def _apply_tool_normalizer(response: Any, log_label: str) -> None:
    raw_cnt = getattr(response, "content", "")
    raw_tc = getattr(response, "tool_calls", None)
    logger.info(f"🔮 [{log_label}] Content: {str(raw_cnt)[:300]} | Tool Calls: {raw_tc}")
    normalized = ToolResponseNormalizer.normalize(raw_content=raw_cnt, existing_tool_calls=raw_tc)
    response.tool_calls = normalized.tool_calls
    if normalized.is_synthesized and normalized.synthesized_sql:
        logger.info(f"✨ [Coder Self-Healing] {log_label}自愈合成为工具调用: {normalized.synthesized_sql[:120]}...")


async def _attempt_mandate_retry(
    prompt: List[BaseMessage],
    response: Any,
    state: Dict[str, Any],
    config: Any,
    tools: List[Any],
) -> Any:
    logger.warning("🚨 [Coder Mandate] 模型未触发工具调用且历史无有效执行数据，触发单刀直入强制执行...")
    raw_response_text = str(getattr(response, "content", ""))
    compact_content = raw_response_text[:200] + ("..." if len(raw_response_text) > 200 else "") if raw_response_text else ""
    retry_prompt = list(prompt) + [AIMessage(content=compact_content), HumanMessage(content=_MANDATE_RETRY_PROMPT)]
    retry_response = await llm_provider.chat(
        role="coder", messages=retry_prompt, config=config, state=state, tools=tools
    )
    _apply_tool_normalizer(retry_response, "Coder Mandate Retry")
    return retry_response if getattr(retry_response, "tool_calls", None) else response


def _build_direct_return_result(
    response: Any,
    state: Dict[str, Any],
    span: Any,
    tracer: Any,
    is_probe_fn: Optional[Callable[[str], bool]],
) -> CoderInferenceResult:
    if hasattr(span, "set_result"):
        span.set_result("未触发工具调用，直接回复")
    history_sql = state.get("sql_history", [])
    preserved_raw_data = state.get("raw_data", "")
    has_valid_execution = state.get("sql_validated", False) and bool(preserved_raw_data)
    core_sql = resolve_core_audit_sql(history_sql, is_probe_fn=is_probe_fn)
    logger.info(f"🔮 [DEBUG_SQL_DIRECT] history_sql={history_sql}, has_valid={has_valid_execution}, core={core_sql[:100]}")
    return CoderInferenceResult(
        response=response,
        has_tool_calls=False,
        direct_return_state={
            "messages": [response],
            "error_log": None if has_valid_execution else (state.get("error_log") or "模型本轮未生成可执行的审计 SQL"),
            "sql_validated": has_valid_execution,
            "execution_trace": tracer.to_legacy_list() if hasattr(tracer, "to_legacy_list") else [],
            "sql_query": core_sql,
            "sql_history": history_sql,
            "raw_data": preserved_raw_data,
        },
    )


async def coordinate_coder_inference(
    prompt: List[BaseMessage],
    state: Dict[str, Any],
    config: Any,
    tools: List[Any],
    span: Any,
    tracer: Any,
    is_probe_fn: Optional[Callable[[str], bool]] = None,
) -> CoderInferenceResult:
    """调度 LLM 思考逻辑并完成协议自愈与强制重试。"""
    response = await llm_provider.chat(
        role="coder", messages=prompt, config=config, state=state, tools=tools, max_tokens=1500
    )
    _apply_tool_normalizer(response, "Coder LLM Response")

    if not getattr(response, "tool_calls", None):
        has_valid_execution = state.get("sql_validated", False) and bool(state.get("raw_data"))
        if not has_valid_execution:
            response = await _attempt_mandate_retry(prompt, response, state, config, tools)

    if not getattr(response, "tool_calls", None):
        return _build_direct_return_result(response, state, span, tracer, is_probe_fn)

    return CoderInferenceResult(response=response, has_tool_calls=True, direct_return_state=None)
