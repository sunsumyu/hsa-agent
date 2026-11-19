"""
app/agents/coder_inference_coordinator.py
=========================================
[Matt Pocock Deep Module & SSOT]
Coder 智能体推理与重试调度协同器 (CoderInferenceCoordinator)。

核心职责：
1. 模型推理发起与输出上限约束 (max_tokens=1500 防无节制思维链延时)
2. 工具调用协议网关规整与多方言自愈 (ToolResponseNormalizer)
3. 缺失工具调用时的脱水压缩与单刀直入强制重试 (Token 脱水 + Mandate Retry)
4. 多轮无工具生成时的安全降级兜底与前序取证保全 (Direct Return)
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable
from loguru import logger
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage

from app.core.llm_provider import llm_provider
from app.core.protocol.tool_normalizer import ToolResponseNormalizer
from app.agents.sql_evidence_resolver import resolve_core_audit_sql


@dataclass
class CoderInferenceResult:
    """推理协同执行产物契约"""
    response: AIMessage
    has_tool_calls: bool
    direct_return_state: Optional[Dict[str, Any]] = None


async def coordinate_coder_inference(
    prompt: List[BaseMessage],
    state: Dict[str, Any],
    config: Any,
    tools: List[Any],
    span: Any,
    tracer: Any,
    is_probe_fn: Optional[Callable[[str], bool]] = None,
) -> CoderInferenceResult:
    """
    调度 LLM 思考逻辑并完成协议自愈与强制重试。
    """
    # 1. 首次 LLM 思考调用
    response = await llm_provider.chat(
        role="coder",
        messages=prompt,
        config=config,
        state=state,
        tools=tools,
        max_tokens=1500  # [Matt Pocock Seam] 精简输出上限，确保 SQL 一次性成型
    )

    raw_cnt = getattr(response, "content", "")
    raw_tc = getattr(response, "tool_calls", None)
    logger.info(f"🔮 [Coder LLM Response] Content: {str(raw_cnt)[:300]} | Tool Calls: {raw_tc}")

    # 2. [协议网关深模块] 统一归一化处理工具调用 (过滤 XML/DSML/CTE/JSON 脏标记与多方言协议)
    normalized = ToolResponseNormalizer.normalize(
        raw_content=raw_cnt,
        existing_tool_calls=raw_tc
    )
    response.tool_calls = normalized.tool_calls
    if normalized.is_synthesized and normalized.synthesized_sql:
        logger.info(f"✨ [Coder Self-Healing] 协议网关自愈合成为工具调用: {normalized.synthesized_sql[:120]}...")

    # 3. 缺失工具调用时的单刀直入强制重试
    if not getattr(response, "tool_calls", None):
        history_sql = state.get("sql_history", [])
        has_valid_execution = state.get("sql_validated", False) and bool(state.get("raw_data"))
        if not has_valid_execution:
            logger.warning("🚨 [Coder Mandate] 模型未触发工具调用且历史无有效执行数据，触发单刀直入强制执行...")
            # [Token 脱水] 压缩未触发工具调用的冗长自然语言回复，避免在重试中携带上千字符无用 CoT
            raw_response_text = str(getattr(response, "content", ""))
            compact_content = raw_response_text[:200] + ("..." if len(raw_response_text) > 200 else "") if raw_response_text else ""
            compact_ai_msg = AIMessage(content=compact_content)
            retry_prompt = list(prompt) + [
                compact_ai_msg,
                HumanMessage(content="【强制执行指令】你尚未物理执行任何有效 SQL 审计查询！严禁仅以自然语言文本回复或反问用户。当前系统已连接真实的 ClickHouse 数据库，所有数据均在库中，请立即调用 `execute_audit_sql` 工具执行对应的物理表查询获取真实统计数据！")
            ]
            retry_response = await llm_provider.chat(
                role="coder",
                messages=retry_prompt,
                config=config,
                state=state,
                tools=tools
            )
            retry_cnt = getattr(retry_response, "content", "")
            retry_tc = getattr(retry_response, "tool_calls", None)
            logger.info(f"🔮 [Coder Mandate Retry] Content: {str(retry_cnt)[:300]} | Tool Calls: {retry_tc}")
            retry_norm = ToolResponseNormalizer.normalize(
                raw_content=retry_cnt,
                existing_tool_calls=retry_tc
            )
            retry_response.tool_calls = retry_norm.tool_calls
            if retry_norm.is_synthesized and retry_norm.synthesized_sql:
                logger.info(f"✨ [Coder Self-Healing] 强制重试自愈合成为工具调用: {retry_norm.synthesized_sql[:120]}...")
            if getattr(retry_response, "tool_calls", None):
                response = retry_response

    # 4. 若最终仍未触发工具调用，直接降级回复
    if not getattr(response, "tool_calls", None):
        if hasattr(span, "set_result"):
            span.set_result("未触发工具调用，直接回复")

        history_sql = state.get("sql_history", [])
        preserved_raw_data = state.get("raw_data", "")
        has_valid_execution = state.get("sql_validated", False) and bool(preserved_raw_data)
        logger.info(f"🔮 [DEBUG_SQL_DIRECT] history_sql from state: {history_sql}, has_valid={has_valid_execution}")
        logger.info(f"🔮 [DEBUG_SQL_DIRECT] preserved_raw_data: {str(preserved_raw_data)[:200]}...")
        core_sql = resolve_core_audit_sql(history_sql, is_probe_fn=is_probe_fn)
        logger.info(f"🔮 [DEBUG_SQL_DIRECT] selected core_sql: {core_sql[:100]}...")

        direct_return_state = {
            "messages": [response],
            "error_log": None if has_valid_execution else (state.get("error_log") or "模型本轮未生成可执行的审计 SQL"),
            "sql_validated": has_valid_execution,
            "execution_trace": tracer.to_legacy_list() if hasattr(tracer, "to_legacy_list") else [],
            "sql_query": core_sql,
            "sql_history": history_sql,
            "raw_data": preserved_raw_data
        }
        return CoderInferenceResult(
            response=response,
            has_tool_calls=False,
            direct_return_state=direct_return_state
        )

    # 5. 成功持有工具调用
    return CoderInferenceResult(
        response=response,
        has_tool_calls=True,
        direct_return_state=None
    )
