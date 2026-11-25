import operator
import os
import re
from typing import Annotated, Dict, List, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
import app.core.logging_config 
import asyncio
import sys

from app.core.state import (
    AuditState,
    AuditFinding,
    AuditReport,
    AuditFeedback,
)
from app.core.registry.schema_registry import schema_registry
from app.core.prompts import CODER_PROMPT
from app.skills.security import SQLGuardian, SecurityViolationError
from app.reporting.report_renderer import report_renderer as _report_renderer
from app.skills.federated.fast_router import RouteType
from app.skills.schema.schema_injector import schema_injector as _schema_injector
from app.core.structured_tracer import StructuredTracer
from app.core.pipeline_tracker import pipeline_tracker  # [V178.10] 管线追踪
from app.core.context.gates import QualityGate
from app.core.config import settings
from app.core.task_pool import task_pool
from langgraph.graph import StateGraph, END

# --- 常量配置 ---
# [Matt Pocock 刚性熔断接缝] 生产交互单轮微调最多 1 次，严禁多轮乒乓死循环
MAX_RETRIES = min(settings.max_agent_retries, 1)

def _record_usage_with_budget(role: str, response: Any, model_id: str, prompt: Any = ""):
    """[兼容性接口] 供外部脚本(如 Benchmark) 拦截或手动记录用量。内部节点已切换至 LLMProvider。"""
    from app.infra.usage_tracker import usage_tracker
    usage = getattr(response, "usage_metadata", {})
    if not usage and hasattr(response, "response_metadata"):
         usage = response.response_metadata.get("token_usage", {})
         
    in_t = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    out_t = usage.get("output_tokens", usage.get("completion_tokens", 0))
    
    usage_tracker.record_usage(model_id, in_t, out_t, prompt=prompt, response_text=str(getattr(response, "content", "")))

# ============================================================
# 节点定义 (全量委托至各 Agent 模块)
# ============================================================

async def planner_node(state: AuditState, config: RunnableConfig):
    """[V168.1] 增加智能路由逻辑的 Planner"""
    from app.agents.planner_agent import planner_agent
    from app.skills.federated.fast_router import fast_router

    pipeline_tracker.on_node_start("PLANNER", state)  # [V178.10]

    # 1. 获取基础信息
    metadata = state.get("metadata") or {}
    user_question = metadata.get("user_question")

    # [SPEC-227 直通分流] 底稿汇编与便签回溯无需规划 SQL，直接放行
    if metadata.get("synthesis_done"):
        result = {
            "tasks": ["直通汇编阶段性审计成果"],
            "methodology": "多轮核查事实汇总与客观度量归集",
            "error_log": None
        }
        pipeline_tracker.on_node_end("PLANNER", state, result)
        return result

    # 检查是否已存在手动指定的 model_id
    manual_model = config.get("configurable", {}).get("model_id")

    # 2. 如果没有手动指定，则执行智能路由分流
    if not manual_model and user_question:
        route = fast_router.classify(user_question)
        logger.info(f"🚦 [SmartRouter] 任务分流决策: {route.model_tier} (原因: {route.reason})")

        # 将路由决策持久化到 Metadata 中，llm_provider.chat 将自动读取
        if "metadata" not in state or state["metadata"] is None:
            state["metadata"] = {}
        state["metadata"]["model_id"] = route.model_tier
        state["metadata"]["routing_info"] = route.reason

    result = await planner_agent.plan(state, config)
    
    # [V2.0 NEW] Gate 1: 校验意图与方法论的一致性
    temp_state = state.copy()
    temp_state.update(result)
    from app.core.context.gates import QualityGate
    validation_res = QualityGate.validate_intent(temp_state)
    if not validation_res.get("passed", True):
        gate_error = validation_res.get("error") or "意图校验失败"
        logger.warning(f"🚨 [Gate 1 Intent Intercept] {gate_error}")
        result["error_log"] = gate_error
        result["retry_count"] = state.get("retry_count", 0) + 1
        result["plan_retry_count"] = state.get("plan_retry_count", 0) + 1
    else:
        result["error_log"] = None
    # 上游规划完成进入 SQLEXEC 前重置单阶段工具调用步数
    result["tool_step_count"] = 0

    pipeline_tracker.on_node_end("PLANNER", state, result)  # [V178.10]
    return result

async def aligner_node(state: AuditState, config: RunnableConfig):
    """[V227.0 SPEC-227 / Matt Pocock Deep Module] 前置白盒语义对齐与长链多轮状态机治理节点"""
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node

    pipeline_tracker.on_node_start("ALIGNER", state)  # [V178.10]
    result = await orchestrate_aligner_node(state, config)
    pipeline_tracker.on_node_end("ALIGNER", state, result)
    return result

async def sqlexec_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 CoderAgent 或 Execution Subgraph 执行工具调用与自愈验证"""
    pipeline_tracker.on_node_start("SQLEXEC", state)  # [V178.10]

    # [Matt Pocock Deep Module] 当开启子图架构时，直接委托给 Execution Subgraph
    if getattr(settings, "use_execution_subgraph", False):
        from app.orchestration.subgraphs.execution_subgraph import execution_engine_node
        res = await execution_engine_node(state, config)
        logger.info(f"🔍 [DEBUG Graph Subgraph] sqlexec_node returned: sql_query = {repr(res.get('sql_query'))}")
        pipeline_tracker.on_node_end("SQLEXEC", state, res)
        return res

    from app.agents.coder_agent import coder_agent
    res = await coder_agent.execute(state, config)
    
    # [V2.0 NEW] Gate 3: 执行结果与原始意图的一致性校验
    if not res.get("error_log"):
        temp_state = state.copy()
        temp_state.update(res)
        from app.core.context.gates import QualityGate
        validation_res = QualityGate.validate_result_matching(temp_state)
        if not validation_res.get("passed", True):
            gate_error = validation_res.get("error") or "结果与意图对齐校验失败"
            logger.warning(f"🚨 [Gate 3 Result Intercept] {gate_error}")
            res["error_log"] = gate_error
            res["retry_count"] = state.get("retry_count", 0) + 1
            res["sql_retry_count"] = state.get("sql_retry_count", 0) + 1

    res["tool_step_count"] = state.get("tool_step_count", 0) + 1
    logger.info(f"🔍 [DEBUG Graph] sqlexec_node returned: sql_query = {repr(res.get('sql_query'))}")
    pipeline_tracker.on_node_end("SQLEXEC", state, res)  # [V178.10]
    return res

async def critic_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ReflectionAgent 执行自愈诊断"""
    from app.agents.reflection_agent import reflection_agent
    pipeline_tracker.on_node_start("CRITIC", state)  # [V178.10]
    result = await reflection_agent.reflect(state, config)
    result["tool_step_count"] = 0
    pipeline_tracker.on_node_end("CRITIC", state, result)  # [V178.10]
    return result

async def reporter_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ReporterNodeOrchestrator 执行报告渲染与事实对齐 [Matt Pocock Deep Module]"""
    logger.info(f"🔍 [DEBUG Graph] reporter_node received: sql_query = {repr(state.get('sql_query'))}")
    pipeline_tracker.on_node_start("REPORTER", state)

    from app.reporting.reporter_node_orchestrator import orchestrate_reporter_node
    result = await orchestrate_reporter_node(state, config, max_retries=MAX_RETRIES)

    pipeline_tracker.on_node_end("REPORTER", state, result)
    return result


async def consolidator_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ConsolidatorAgent 执行经验固化"""
    from app.agents.consolidator_agent import consolidator_agent
    pipeline_tracker.on_node_start("CONSOLIDATOR", state)  # [V178.10]
    metadata = state.get("metadata") or {}
    if metadata.get("synthesis_done"):
        result = {"error_log": None}
        pipeline_tracker.on_node_end("CONSOLIDATOR", state, result)
        return result
    result = await consolidator_agent.consolidate(state)
    pipeline_tracker.on_node_end("CONSOLIDATOR", state, result)  # [V178.10]
    return result

async def human_approval_node(state: AuditState, config: RunnableConfig):
    """[V173.1] 人机协作拦截点：将任务提交至动态任务池并挂起"""
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    reason = state.get("error_log") or "触发高风险审计门控，需要人工复核"
    
    # 提交至任务池
    task_pool.submit_task(thread_id, state, reason)
    
    return {
        "is_awaiting_human": True,
        "next_step": "AWAITING_REVISION",
        "error_log": f"已挂起：{reason}"
    }

# ============================================================
# 路由逻辑与工作流构建 (委托至 graph_route_coordinator 深模块)
# ============================================================
from app.orchestration.graph_route_coordinator import (
    route_aligner_post as _route_aligner_post,
    route_planner_post as _route_planner_post,
    route_critic_post as _route_critic_post,
    route_sqlexec_post as _route_sqlexec_post,
)

def _build_workflow_skeleton() -> StateGraph:
    wf = StateGraph(AuditState)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("ALIGNER", aligner_node)
    wf.add_node("SQLEXEC", sqlexec_node)
    wf.add_node("CRITIC", critic_node)
    wf.add_node("REPORTER", reporter_node)
    wf.add_node("CONSOLIDATOR", consolidator_node)
    wf.add_node("HUMAN_APPROVAL", human_approval_node)

    wf.set_entry_point("ALIGNER")
    wf.add_conditional_edges(
        "ALIGNER",
        _route_aligner_post,
        {
            "PLANNER": "PLANNER",
            "REPORTER": "REPORTER",
        },
    )
    # [V2.0 NEW] 使用条件路由连接 PLANNER 与下一跳
    wf.add_conditional_edges(
        "PLANNER",
        _route_planner_post,
        {
            "CRITIC": "CRITIC",
            "SQLEXEC": "SQLEXEC",
            "CONSOLIDATOR": "CONSOLIDATOR"
        }
    )
    wf.add_conditional_edges(
        "SQLEXEC", 
        _route_sqlexec_post, 
        {
            "SQLEXEC": "SQLEXEC", 
            "CRITIC": "CRITIC", 
            "CONSOLIDATOR": "CONSOLIDATOR",
            "HUMAN_APPROVAL": "HUMAN_APPROVAL"  # 正常路由到审批节点
        }
    )
    wf.add_edge("HUMAN_APPROVAL", END) # 审批节点是自动流程的终点
    # [V2.0 NEW] 使用条件路由决定 CRITIC 纠偏后的下一跳
    wf.add_conditional_edges(
        "CRITIC",
        _route_critic_post,
        {
            "PLANNER": "PLANNER",
            "SQLEXEC": "SQLEXEC",
            "CONSOLIDATOR": "CONSOLIDATOR",
        }
    )
    wf.add_edge("CONSOLIDATOR", "REPORTER")
    wf.add_edge("REPORTER", END)
    return wf

def build_graph():
    return _build_workflow_skeleton().compile()

workflow = build_graph()

def get_graph_executor(checkpointer=None, model_id: Optional[str] = None):
    executor = _build_workflow_skeleton().compile(checkpointer=checkpointer) if checkpointer else workflow
    return executor, (model_id or "default")

class AgentGraph:
    def __init__(self, model_id: str = None): self.model_id = model_id
    def compile(self, checkpointer=None): return workflow
