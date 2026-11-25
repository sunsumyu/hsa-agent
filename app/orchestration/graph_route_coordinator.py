from typing import Optional
from loguru import logger
from langchain_core.messages import ToolMessage
from app.core.state import AuditState
from app.core.context.gates import QualityGate
from app.core.config import settings

# [Matt Pocock 刚性熔断接缝] 生产交互单轮微调最多 1 次，严禁多轮乒乓死循环
MAX_RETRIES = min(settings.max_agent_retries, 1)
# 单次 SQLEXEC 阶段最大工具调用步数，防止 ReAct 复读机死循环
MAX_TOOL_STEPS = 5


def route_aligner_post(state: AuditState) -> str:
    """ALIGNER 后的条件路由：非取证直通响应（synthesis_done）直达 REPORTER，否则进入 PLANNER。"""
    metadata = state.get("metadata") or {}
    if metadata.get("synthesis_done"):
        logger.info("⚡ [Graph Route] ALIGNER 命中直通分流，跳过 PLANNER/CONSOLIDATOR 直达 REPORTER。")
        return "REPORTER"
    return "PLANNER"


def route_planner_post(state: AuditState, max_retries: int = MAX_RETRIES) -> str:
    """[V2.0 NEW / Matt Pocock Deep Module] Planner 后的条件路由：若 Gate 1 校验失败则自愈，超限则熔断"""
    metadata = state.get("metadata") or {}
    if metadata.get("synthesis_done"):
        return "CONSOLIDATOR"
    if state.get("error_log"):
        if state.get("plan_retry_count", 0) > max_retries or state.get("retry_count", 0) > max_retries:
            logger.warning("🛑 [Graph Route] PLANNER 规划重试已达上限，熔断直通 CONSOLIDATOR 降级汇总。")
            return "CONSOLIDATOR"
        logger.info("🔄 [Graph Route] Gate 1 意图校验失败，走向 CRITIC 自愈。")
        return "CRITIC"
    return "SQLEXEC"


def route_critic_post(state: AuditState, max_retries: int = MAX_RETRIES) -> str:
    """[V2.0 NEW / Matt Pocock Deep Module] CRITIC 后的条件路由：区分意图错误与执行错误，并校验熔断上限"""
    err = state.get("error_log", "")
    is_intent_error = bool(
        err
        and (
            "方法论" in err
            or "意图" in err
            or "Gate 1" in err
            or "RANKING" in err
            or (
                "SQL 语义错误" in err
                and "RANKING" in state.get("metadata", {}).get("semantic_alignment", {}).get("query_type", "")
            )
        )
    )
    if is_intent_error:
        if state.get("plan_retry_count", 0) > max_retries or state.get("retry_count", 0) > max_retries:
            logger.warning("🛑 [Graph Route] CRITIC 意图纠偏已达上限，熔断直通 CONSOLIDATOR。")
            return "CONSOLIDATOR"
        logger.info("🔄 [Graph Route] CRITIC 诊断为意图方法论错误，重新进入 PLANNER。")
        return "PLANNER"

    if state.get("sql_retry_count", 0) > max_retries or state.get("retry_count", 0) > max_retries:
        logger.warning("🛑 [Graph Route] CRITIC 执行纠偏已达上限，熔断直通 CONSOLIDATOR。")
        return "CONSOLIDATOR"
    logger.info("🔄 [Graph Route] CRITIC 诊断为执行错误，重新进入 SQLEXEC。")
    return "SQLEXEC"


def route_sqlexec_post(
    state: AuditState,
    max_retries: int = MAX_RETRIES,
    max_tool_steps: int = MAX_TOOL_STEPS,
) -> str:
    """[V2.0 NEW / Matt Pocock Deep Module] SQLEXEC 后的条件路由决策中心"""
    # 0. 快速路由物理直通分流：直接走向 Consolidator，避免二次 LLM 工具综合与循环
    metadata = state.get("metadata") or {}
    if metadata.get("fast_route_id") or metadata.get("synthesis_done"):
        return "CONSOLIDATOR"

    # 如果执行阶段发生错误（包括 Gate 2 拦截或执行报错），且未超限，优先走向 CRITIC 纠偏
    if (state.get("error_log") or state.get("has_error")) and state.get("retry_count", 0) < max_retries:
        logger.info("🔄 [Graph Route] SQLEXEC 校验/执行失败，走向 CRITIC 纠偏。")
        return "CRITIC"

    # [Matt Pocock 极简单一接缝] 若已完成物理取证且无错误，直接前往 CONSOLIDATOR 组织报告，斩断二次 LLM 冗余复述
    if state.get("sql_validated") and state.get("raw_data") and not state.get("error_log"):
        logger.info("🎯 [Graph Route] 物理取证已成功锁定，直接走向 CONSOLIDATOR，避免冗余多轮推理。")
        return "CONSOLIDATOR"

    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    # 1. 如果还在调工具，检查步数上限与重试上限后继续在 SQLEXEC 思考
    if isinstance(last_msg, ToolMessage) or (not isinstance(last_msg, tuple) and getattr(last_msg, "tool_calls", None)):
        if state.get("tool_step_count", 0) >= max_tool_steps:
            logger.warning(f"🛑 [Graph Route] SQLEXEC 工具调用达到上限 ({max_tool_steps})，强制退出循环进入 CONSOLIDATOR。")
            return "CONSOLIDATOR"
        if state.get("retry_count", 0) < max_retries:
            return "SQLEXEC"

    # 1.5 风险截断：如果风险过高，强制进入待审批状态
    if QualityGate.should_trigger_human_approval(state):
        return "HUMAN_APPROVAL"

    # 2. 增强门控：检查错误日志或元数据信心值
    if QualityGate.should_trigger_critic(state) and state.get("retry_count", 0) < max_retries:
        return "CRITIC"
        
    return "CONSOLIDATOR"
