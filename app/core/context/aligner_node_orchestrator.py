from typing import Dict, Any, Optional
from loguru import logger
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from app.core.state import AuditState
from app.agents.sql_evidence_resolver import resolve_user_query
from app.core.context.coreference_rewriter import coreference_rewriter
from app.core.context.direct_turn_handler import handle_direct_turn
from app.core.context.funnel import semantic_funnel


async def orchestrate_aligner_node(state: AuditState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """[V227.0 SPEC-227 / Matt Pocock Deep Module] 
    前置白盒语义对齐、多轮指代消解、非取证直通与单轮状态清洗的深层编排器。
    
    隐藏实现细节：
    - 多来源用户提问兼容性提取与兜底回退
    - 指代消解与意图分类
    - 问候/元语意图与直通分支的分流
    - 快速路由 L0.5 旁路跳过语义对齐漏斗
    - 语义白盒漏斗调用、元数据装配与上一轮中间临时状态清洗
    """
    # 1. 逆向提取最新人类消息作为当前轮用户提问 (SPEC-227 SSOT 与宽容性接口对齐)
    raw_input = resolve_user_query(
        state, 
        fallback_keys=["user_prompt", "user_query", "human_input", "question", "prompt", "query"]
    )

    if not raw_input:
        logger.warning("[AlignerNode] 未能从状态中提取到有效的用户提问，跳过对齐流")
        return {}

    # 2. [SPEC-227/V228] 执行上下文指代消解与任务意图分类
    # (TurnAnalysis 数据类契约，通过 __iter__ 兼容旧三元组解包，真实返回与测试 mock 返回均可消费)
    resolved_query, turn_type, key_entities = coreference_rewriter.resolve_coreference(raw_input, state)
    user_input = resolved_query
    logger.info(f"🧭 [AlignerNode] 当前轮次意图分类: {turn_type} | 命题消解: 「{user_input[:50]}...」")

    metadata = dict(state.get("metadata") or {})
    metadata["user_question"] = user_input
    metadata["turn_type"] = turn_type

    # 3. [SPEC-227 / Matt Pocock Deep Module] 非数据取证类直通分支委托处理
    direct_result = handle_direct_turn(
        user_input=user_input,
        turn_type=turn_type,
        key_entities=key_entities,
        state=state,
        metadata=metadata,
    )
    if direct_result is not None:
        return direct_result

    # 4. 数据取证型任务 (QUERY) -> 重置单轮临时状态并进入对齐漏斗
    try:
        fast_route_id = metadata.get("fast_route_id")
        normalized_msgs = [HumanMessage(content=user_input)] if not state.get("messages") else []

        if fast_route_id:
            logger.success("⚡ [Aligner Bypass] 智能体命中直通分支，跳过语义对齐漏斗")
            return {
                "current_turn_query": user_input,
                "turn_type": turn_type,
                "metadata": metadata,
                "messages": normalized_msgs
            }

        alignment_report = await semantic_funnel.execute_alignment_flow(user_input, config)

        metadata_update = {
            **metadata,
            "semantic_alignment": alignment_report,
            "user_question": user_input
        }
        temp_table = alignment_report.get("temp_table")

        logger.success(f"🎯 [AlignerNode] 语义白盒漏斗对齐成功，临时表: {temp_table}")
        return {
            "current_turn_query": user_input,
            "turn_type": turn_type,
            "metadata": metadata_update,
            "temp_table": temp_table,
            "schema_hint": alignment_report.get("explanation"),
            "messages": normalized_msgs,
            # [SPEC-227 状态清洗] 新轮次清空上一轮遗留的中间临时状态
            "raw_data": "",
            "sql_query": "",
            "sql_validated": False,
            "error_log": None,
            "retry_count": 0
        }

    except Exception as e:
        logger.error(f"❌ [AlignerNode] 对齐流执行异常: {e}")
        return {}
