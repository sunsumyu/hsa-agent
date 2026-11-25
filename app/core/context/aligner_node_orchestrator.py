from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from app.core.state import AuditState
from app.core.sql_evidence_resolver import resolve_user_query
from app.core.context.coreference_rewriter import coreference_rewriter
from app.core.context.direct_turn_handler import handle_direct_turn
from app.core.context.funnel import semantic_funnel
from app.multi_agent.contracts import ExecutionTier
from app.multi_agent.tier_classifier import classify_execution_plan
from app.skills.federated.fast_router import RouteType, fast_router


async def _resolve_user_input(
    state: AuditState,
    config: Optional[RunnableConfig],
) -> Optional[Tuple[str, str, List[Any]]]:
    raw_input = resolve_user_query(
        state,
        fallback_keys=["user_prompt", "user_query", "human_input", "question", "prompt", "query"],
    )
    if not raw_input:
        logger.warning("[AlignerNode] 未能从状态中提取到有效的用户提问，跳过对齐流")
        return None
    resolved_query, turn_type, key_entities = coreference_rewriter.resolve_coreference(raw_input, state)
    if coreference_rewriter.needs_llm_coreference_fallback(raw_input, resolved_query, turn_type, state):
        resolved_query = await coreference_rewriter.llm_fallback_rewrite(raw_input, state, config=config)
    logger.info(f"🧭 [AlignerNode] 当前轮次意图分类: {turn_type} | 命题消解: 「{resolved_query[:50]}...」")
    return resolved_query, turn_type, key_entities


async def _run_semantic_alignment(
    user_input: str,
    turn_type: str,
    metadata: Dict[str, Any],
    normalized_msgs: List[HumanMessage],
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    alignment_report = await semantic_funnel.execute_alignment_flow(user_input, config)
    metadata_update = {
        **metadata,
        "semantic_alignment": alignment_report,
        "user_question": user_input,
    }
    tier_plan = classify_execution_plan(user_input, metadata_update)
    if tier_plan.tier != ExecutionTier.L2_MULTI_AGENT and not metadata_update.get("fast_route_id"):
        route = fast_router.classify(user_input)
        if route.route_type != RouteType.UNKNOWN:
            metadata_update["fast_route_id"] = route.target_id
            tier_plan = classify_execution_plan(user_input, metadata_update)
    metadata_update["execution_tier"] = tier_plan.tier.value
    metadata_update["execution_plan"] = tier_plan.model_dump(mode="json")
    temp_table = alignment_report.get("temp_table")
    logger.success(f"🎯 [AlignerNode] 语义白盒漏斗对齐成功，临时表: {temp_table}")
    return {
        "current_turn_query": user_input,
        "turn_type": turn_type,
        "metadata": metadata_update,
        "temp_table": temp_table,
        "schema_hint": alignment_report.get("explanation"),
        "messages": normalized_msgs,
        "raw_data": "",
        "sql_query": "",
        "sql_validated": False,
        "error_log": None,
        "retry_count": 0,
        "plan_retry_count": 0,
        "sql_retry_count": 0,
        "tool_step_count": 0,
    }


async def orchestrate_aligner_node(state: AuditState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """前置白盒语义对齐、多轮指代消解、非取证直通与单轮状态清洗的深层编排器。"""
    resolved = await _resolve_user_input(state, config)
    if resolved is None:
        return {}
    user_input, turn_type, key_entities = resolved

    metadata = {**(state.get("metadata") or {}), "user_question": user_input, "turn_type": turn_type}
    direct_result = handle_direct_turn(
        user_input=user_input,
        turn_type=turn_type,
        key_entities=key_entities,
        state=state,
        metadata=metadata,
    )
    if direct_result is not None:
        return direct_result

    try:
        normalized_msgs = [HumanMessage(content=user_input)] if not state.get("messages") else []
        if metadata.get("fast_route_id"):
            tier_plan = classify_execution_plan(user_input, metadata)
            logger.success("⚡ [Aligner Bypass] 智能体命中直通分支，跳过语义对齐漏斗")
            return {
                "current_turn_query": user_input,
                "turn_type": turn_type,
                "metadata": {
                    **metadata,
                    "execution_tier": tier_plan.tier.value,
                    "execution_plan": tier_plan.model_dump(mode="json"),
                },
                "messages": normalized_msgs,
            }
        return await _run_semantic_alignment(user_input, turn_type, metadata, normalized_msgs, config)
    except Exception as e:
        logger.error(f"❌ [AlignerNode] 对齐流执行异常: {e}")
        return {}
