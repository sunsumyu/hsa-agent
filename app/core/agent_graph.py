import operator
import re
from typing import Annotated, Sequence, TypedDict, Dict, List, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
import app.core.logging_config 
import asyncio
import sys

from app.core.state import (
    AuditState as _LayeredAuditState,
    AuditFinding as _LayeredAuditFinding,
    AuditReport as _LayeredAuditReport,
    AuditFeedback as _LayeredAuditFeedback,
)
from app.core.registry.schema_registry import schema_registry
from app.core.prompts import CODER_PROMPT
from app.skills.security import SQLGuardian, SecurityViolationError
from app.memory.message_sanitizer import trim_and_sanitize
from app.reporting.report_renderer import report_renderer as _report_renderer
from app.skills.fast_router import RouteType
from app.skills.schema_injector import schema_injector as _schema_injector
from app.core.structured_tracer import StructuredTracer
from app.core.context.gates import QualityGate
from app.core.config import settings
from app.core.task_pool import task_pool
from langgraph.graph import StateGraph, END

# --- 常量配置 ---
MAX_RETRIES = settings.max_agent_retries

def _record_usage_with_budget(role: str, response: Any, model_id: str, prompt: Any = ""):
    """[兼容性接口] 供外部脚本(如 Benchmark) 拦截或手动记录用量。内部节点已切换至 LLMProvider。"""
    from app.infra.usage_tracker import usage_tracker
    usage = getattr(response, "usage_metadata", {})
    if not usage and hasattr(response, "response_metadata"):
         usage = response.response_metadata.get("token_usage", {})
         
    in_t = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    out_t = usage.get("output_tokens", usage.get("completion_tokens", 0))
    
    usage_tracker.record_usage(model_id, in_t, out_t, prompt=prompt, response_text=str(getattr(response, "content", "")))

def _trim_messages(left: List, right: List) -> List:
    return trim_and_sanitize(left, right, max_total=15, keep_head=3, keep_tail=7)

def _merge_dict(left: Dict, right: Dict) -> Dict:
    new = (left or {}).copy()
    new.update(right or {})
    return new

def _merge_list(left: List, right: List) -> List:
    return (left or []) + (right or [])

class AuditState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], _trim_messages]
    tasks: List[str]
    sql_query: str
    sql_history: Annotated[List[str], _merge_list]  # [V178.9] 全量 SQL 证据链
    raw_data: str
    audit_findings: List[_LayeredAuditFinding]
    structured_report: Optional[_LayeredAuditReport]
    metadata: Annotated[Dict[str, Any], _merge_dict]
    session_id: str
    error_log: str
    audit_feedback: Optional[_LayeredAuditFeedback]
    retry_count: int
    human_input: Optional[str]
    is_awaiting_human: bool
    sql_validated: bool
    loop_count: int
    next_step: str
    schema_hint: Optional[str]
    execution_trace: List[str]
    methodology: str
    temp_table: Optional[str]

# ============================================================
# 节点定义 (全量委托至各 Agent 模块)
# ============================================================

async def planner_node(state: AuditState, config: RunnableConfig):
    """[V168.1] 增加智能路由逻辑的 Planner"""
    from app.agents.planner_agent import planner_agent
    from app.skills.fast_router import fast_router

    # 1. 获取基础信息
    metadata = state.get("metadata") or {}
    user_question = metadata.get("user_question")
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

    return await planner_agent.plan(state, config)

async def aligner_node(state: AuditState, config: RunnableConfig):
    """[V210.0] 前置白盒语义对齐节点 AlignerNode"""
    from app.core.context.funnel import semantic_funnel
    from langchain_core.messages import HumanMessage
    
    # 1. 提取用户审计提问
    user_input = ""
    for msg in state.get("messages", []):
        if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
            user_input = msg[1] if isinstance(msg, tuple) else str(msg.content)
            break
            
    if not user_input:
        logger.warning("[AlignerNode] 未能从状态中提取到有效的用户提问，跳过对齐流")
        return {}
        
    # 2. 执行穿透四层语义漏斗流程
    try:
        alignment_report = await semantic_funnel.execute_alignment_flow(user_input, config)
        
        # 3. 构造状态更新
        metadata_update = {
            "semantic_alignment": alignment_report,
            "user_question": user_input
        }
        
        # 提取临时表，写入 state
        temp_table = alignment_report.get("temp_table")
        
        logger.success(f"🎯 [AlignerNode] 语义白盒漏斗对齐成功，临时表: {temp_table}")
        return {
            "metadata": metadata_update,
            "temp_table": temp_table,
            "schema_hint": alignment_report.get("explanation")
        }
    except Exception as e:
        logger.error(f"❌ [AlignerNode] 对齐流执行异常: {e}")
        return {}

async def sqlexec_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 CoderAgent 执行工具调用与验证"""
    from app.agents.coder_agent import coder_agent
    return await coder_agent.execute(state, config)

async def critic_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ReflectionAgent 执行自愈诊断"""
    from app.agents.reflection_agent import reflection_agent
    return await reflection_agent.reflect(state, config)

async def reporter_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ReportRenderer 执行报告渲染与事实对齐"""
    from app.reporting.report_renderer import report_renderer
    from app.core.booster import booster
    from app.core.registry.schema_registry import schema_registry
    from app.core.llm_provider import llm_provider
    from langchain_core.messages import HumanMessage, AIMessage

    logger.info(">>> [REPORTER] 正在执行渲染任务...")
    raw_data_list = report_renderer.clean_and_parse_raw_data(state.get("raw_data"))
    hard_sum = sum(float(r.get("medfee_sumamt", r.get("amount", 0))) for r in raw_data_list)
    hard_count = len(raw_data_list)
    
    user_question = (state.get("metadata") or {}).get("user_question") or "医保专项审计"
    
    # [V156.0] 提取最后一条 AI 消息的元数据作为溯源证据
    messages = state.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    audit_meta = getattr(last_ai, "additional_kwargs", {}) if last_ai else {}
    
    methodology = state.get("methodology", "基础核查逻辑")
    execution_trace = state.get("execution_trace") or []

    prompt_text = report_renderer.prepare_conclusion_prompt(user_question, methodology, execution_trace, hard_count, hard_sum)
    try:
        response = await llm_provider.chat(
            role="reporter", 
            messages=[HumanMessage(content=prompt_text)], 
            config=config, 
            state=state,
            max_tokens=1000 # [V178.9] 防止长篇专业结论被物理截断
        )
        llm_conclusion = str(response.content).strip()
    except Exception as e:
        logger.error(f"结论生成失败: {e}")
        llm_conclusion = f"本次核查扫描 {hard_count} 条记录，涉及金额 ¥{hard_sum:,.2f}。"

    rendered = report_renderer.render(
        user_question=user_question,
        llm_conclusion=llm_conclusion,
        raw_data=raw_data_list,
        sql_query=state.get("sql_query"),
        sql_history=state.get("sql_history", []), # [V178.9] 传入全量 SQL 历史
        methodology=methodology,
        table_info=f"{schema_registry.get_main_table()}",
        total_amount=hard_sum,
        finding_count=hard_count,
        execution_trace=execution_trace,
        audit_metadata=audit_meta, # [V156.0]
        semantic_alignment=(state.get("metadata") or {}).get("semantic_alignment") # [NEW]
    )

    is_aligned, _ = booster.verify_semantic_alignment(state.get("sql_query"), llm_conclusion)
    if not is_aligned: logger.warning("🚨 [SEMANTIC_MISMATCH] 报告语义偏离")

    return {"structured_report": rendered, "messages": [AIMessage(content=rendered.markdown)]}

async def consolidator_node(state: AuditState, config: RunnableConfig):
    """[V150.0] 委托至 ConsolidatorAgent 执行经验固化"""
    from app.agents.consolidator_agent import consolidator_agent
    return await consolidator_agent.consolidate(state)

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
# 路由逻辑与工作流构建
# ============================================================

def _route_sqlexec_post(state: AuditState) -> str:
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    # 1. 如果还在调工具，继续在 SQLEXEC 思考
    if isinstance(last_msg, ToolMessage) or (not isinstance(last_msg, tuple) and getattr(last_msg, "tool_calls", None)):
        if state.get("retry_count", 0) < MAX_RETRIES: return "SQLEXEC"

    # 1.5 风险截断：如果风险过高，强制进入待审批状态
    if QualityGate.should_trigger_human_approval(state):
        return "HUMAN_APPROVAL"

    # 2. 增强门控：检查错误日志或元数据信心值
    if QualityGate.should_trigger_critic(state) and state.get("retry_count", 0) < MAX_RETRIES:
        return "CRITIC"
        
    return "CONSOLIDATOR"

def _build_workflow_skeleton() -> StateGraph:
    wf = StateGraph(AuditState)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("ALIGNER", aligner_node)
    wf.add_node("SQLEXEC", sqlexec_node)
    wf.add_node("CRITIC", critic_node)
    wf.add_node("REPORTER", reporter_node)
    wf.add_node("CONSOLIDATOR", consolidator_node)
    wf.add_node("HUMAN_APPROVAL", human_approval_node)

    wf.set_entry_point("PLANNER")
    wf.add_edge("PLANNER", "ALIGNER")
    wf.add_edge("ALIGNER", "SQLEXEC")
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
    wf.add_edge("CRITIC", "SQLEXEC")
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
