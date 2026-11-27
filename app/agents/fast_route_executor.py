"""
app/agents/fast_route_executor.py
=================================
[Matt Pocock Deep Module & SSOT]
快速路由执行器 (FastRouteExecutor)。

核心职责：
1. 检测 state.metadata 中的 fast_route_id。若无则以 handled=False 立即返回。
2. 构造工具调用 payload (audit_medical_rule)，跳过 LLM Coder 生成阶段。
3. 调用 audit_tool_executor 物理执行工具集，并由 tool_evidence_extractor 进行标准化清洗。
4. 零行回退分流 (Fast Route Fallback)：
   若执行结果集为空 (raw_data 为空/None/[] 且无错误)，说明预定义静态规则未能命中当前数据集。
   自动剔除 fast_route_id 标记，记录已尝试 SQL 到 sql_history，并返回 fallback_to_llm=True，
   使执行流平滑降级到 LLM 动态推理路径。
5. 若执行成功或遇到显式错误，直接组装状态输出字典，返回 handled=True, fallback_to_llm=False。
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable, Tuple
from loguru import logger
from langchain_core.messages import AIMessage

from app.core.structured_tracer import StructuredTracer
from app.agents.audit_tool_executor import invoke_tools_safely
from app.core.tool_engine.tool_evidence_extractor import tool_evidence_extractor


@dataclass
class FastRouteExecutionResult:
    """快速路由执行结果契约"""
    handled: bool
    fallback_to_llm: bool = False
    state_update: Optional[Dict[str, Any]] = None


def _build_fast_route_payload(
    fast_route_id: str,
    metadata: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], AIMessage]:
    """构造静态规则直通工具调用参数与占位 AI 消息。"""
    tool_calls = [{
        "name": "audit_medical_rule",
        "args": {
            "rule_id": fast_route_id,
            "extra_filters": metadata.get("extra_filters"),
        },
        "id": f"call_fast_route_{fast_route_id}",
    }]
    response = AIMessage(
        content=f"已通过快速路由匹配到静态审计规则: {fast_route_id}，正在执行物理直通计算。",
        tool_calls=tool_calls,
    )
    return tool_calls, response


def _apply_zero_row_fallback(
    state: Dict[str, Any],
    metadata: Dict[str, Any],
    fast_route_id: str,
    processed: Dict[str, Any],
) -> FastRouteExecutionResult:
    """零行结果时清除快速路由标记并记录 SQL 历史以回退 LLM 推理。"""
    logger.warning(
        f"⚡ [Fast Route Fallback] 规则 {fast_route_id} 物理执行返回 0 行，"
        f"数据集与模板不匹配，自动降级到 LLM 推理路径以动态适配。"
    )
    metadata.pop("fast_route_id", None)
    state["metadata"] = metadata
    state.setdefault("sql_history", [])
    if processed.get("sql_query"):
        state["sql_history"].append(processed["sql_query"])

    return FastRouteExecutionResult(handled=True, fallback_to_llm=True, state_update=None)


def _build_fast_route_state_update(
    response: AIMessage,
    processed: Dict[str, Any],
    retry: int,
    tracer: StructuredTracer,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """装配快速路由命中或报错时的状态更新字典。"""
    return {
        "raw_data": processed.get("raw_data"),
        "sql_query": processed.get("sql_query"),
        "sql_history": processed.get("sql_history"),
        "methodology": processed.get("methodology"),
        "messages": [response] + processed.get("tool_msgs", []),
        "retry_count": retry,
        "sql_validated": not processed.get("has_error"),
        "error_log": processed.get("error_msg") if processed.get("has_error") else None,
        "execution_trace": tracer.to_legacy_list(),
        "temp_table": state.get("temp_table"),
    }


async def execute_fast_route_bypass(
    state: Dict[str, Any],
    tools: List[Any],
    tracer: StructuredTracer,
    retry: int = 0,
    is_probe_fn: Optional[Callable[[str], bool]] = None,
) -> FastRouteExecutionResult:
    """
    执行快速路由物理直通分流与零行回退判定。
    """
    metadata = state.get("metadata") or {}
    fast_route_id = metadata.get("fast_route_id")
    if not fast_route_id:
        return FastRouteExecutionResult(handled=False)

    logger.success(f"⚡ [Coder Bypass] 智能体命中直通分支，跳过 Coder LLM 生成，直接物理调用工具: {fast_route_id}")
    tool_calls, response = _build_fast_route_payload(fast_route_id, metadata)

    with tracer.span("SQL_EXECUTION", node="CODER") as span:
        results = await invoke_tools_safely(
            tool_calls=tool_calls,
            tools=tools,
            state=state,
            is_probe_fn=is_probe_fn,
        )
        span.set_result(f"物理执行完成，获取 {len(results)} 组结果集")

    processed = tool_evidence_extractor.process(results, state).to_dict()
    raw = processed.get("raw_data", "")
    is_empty_result = not raw or str(raw).strip() in ("", "[]", "None")
    if is_empty_result and not processed.get("has_error"):
        return _apply_zero_row_fallback(state, metadata, fast_route_id, processed)

    state_update = _build_fast_route_state_update(response, processed, retry, tracer, state)
    return FastRouteExecutionResult(handled=True, fallback_to_llm=False, state_update=state_update)
