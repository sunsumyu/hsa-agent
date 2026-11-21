# -*- coding: utf-8 -*-
"""
app/core/subgraphs/execution_subgraph.py
========================================
[Matt Pocock Deep Module / Seam Isolation]
数据执行与局部自愈子图 (Execution & Self-Healing Subgraph)

设计理念与架构特性：
1. 信息隐藏 (Information Hiding)：
   将 Coder 与 Critic 之间的自愈微循环、中间报错日志、临时 SQL 历史、重试计数器完全封装在子图内部。
2. 窄接缝 (Minimal Seam)：
   向父图暴露标准 LangGraph 节点函数 execution_engine_node，仅向父图输出干净的契约交付物 (sql_query, raw_data, sql_validated 等)。
3. 双向自愈与逃生舱 (Self-Healing & Escape Hatch)：
   Coder 执行完毕后经由 Gate 门控（Gate 3 结果对齐校验），若异常则进入 Critic 诊断修正；
   达到 max_retries 阈值后强制走逃生舱退出，根除顶层图无限死循环风险。
"""

from __future__ import annotations

from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    TypedDict,
)

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from loguru import logger


# ── 1. 子图私有状态契约 ───────────────────────────────────────

class ExecutionSubState(TypedDict, total=False):
    """
    [Matt Pocock Deep Module] 子图独立状态定义。
    
    包含子图私有内部诊断字段，彻底解耦父图 AuditState 的膨胀。
    """
    # ── 外部上下文输入 (Read-Only Context)
    tasks: Optional[List[str]]
    methodology: Optional[str]
    metadata: Optional[Dict[str, Any]]
    session_id: Optional[str]
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ── 内部私有自愈状态 (Information Hiding, 严禁泄露至父图)
    retry_count: int
    max_retries: int
    sql_history: List[str]
    error_log: Optional[str]
    internal_critic_log: Optional[str]

    # ── 子图对外交付物 (Public Deliverables)
    sql_query: Optional[str]
    final_sql: Optional[str]
    raw_data: Optional[Any]
    evidence_row_count: Optional[int]  # [\u8bc1\u636e\u5bf9\u8d26] \u8bc1\u636e\u901a\u9053\u53ef\u89e3\u6790\u884c\u6570\uff08Append-Only \u7d2f\u52a0\uff09
    sql_validated: Optional[bool]
    execution_trace: Optional[List[str]]
    temp_table: Optional[str]
    is_awaiting_human: Optional[bool]


# ── 2. 子图内部微节点实现 ─────────────────────────────────────

async def coder_step(
    state: ExecutionSubState, 
    config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """
    [Coder Agent 步骤]
    委托给 coder_agent 执行 SQL 生成与数据查询。
    维护子图内部私有 sql_history 与局部 execution_trace。
    """
    from app.agents.coder_agent import coder_agent

    logger.debug(
        f"[ExecutionSubgraph:CODER] Invoking coder_agent (retry={state.get('retry_count', 0)})"
    )
    res = await coder_agent.execute(state, config)
    patch: Dict[str, Any] = dict(res or {})

    # 维护内部私有 SQL 历史 (自愈对比基准)
    sql_history = list(state.get("sql_history") or [])
    current_sql = patch.get("sql_query") or patch.get("final_sql")
    if current_sql and current_sql not in sql_history:
        sql_history.append(current_sql)
    patch["sql_history"] = sql_history

    # 维护执行足迹
    execution_trace = list(state.get("execution_trace") or [])
    retry_idx = state.get("retry_count", 0)
    execution_trace.append(f"coder_exec_v{retry_idx}")
    patch["execution_trace"] = execution_trace

    return patch


async def gate_step(
    state: ExecutionSubState, 
    config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """
    [Gate 3 质量门控步骤]
    校验执行结果与审计意图的语义对齐度。
    若 Coder 产生底层错误或 Gate 拦截，标记 sql_validated=False 并记录 error_log。
    """
    # 1. 若 Coder 执行底层已报错或校验标记为 False
    if state.get("error_log") or state.get("sql_validated") is False:
        logger.warning(
            f"[ExecutionSubgraph:GATE] Fast-failing gate: error_log={state.get('error_log')}"
        )
        return {
            "sql_validated": False,
            "error_log": state.get("error_log") or "SQL 执行未通过校验",
        }

    # 2. 调用 QualityGate 进行语义与意图匹配校验
    from app.core.context.gates import QualityGate
    temp_state = dict(state)
    validation_res = QualityGate.validate_result_matching(temp_state)

    if isinstance(validation_res, dict) and not validation_res.get("passed", True):
        gate_error = validation_res.get("error") or "结果与意图对齐校验失败"
        logger.warning(f"🚨 [ExecutionSubgraph:GATE Intercept] {gate_error}")
        return {
            "sql_validated": False,
            "error_log": gate_error,
        }

    logger.debug("[ExecutionSubgraph:GATE] Quality gate passed successfully")
    return {
        "sql_validated": True,
        "error_log": None,
    }


async def critic_step(
    state: ExecutionSubState, 
    config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """
    [Critic 自愈诊断步骤]
    委托给 reflection_agent 分析错误原因并产出纠偏指导。
    自动保证 retry_count 递增以防死循环。
    """
    from app.agents.reflection_agent import reflection_agent

    logger.info(
        f"[ExecutionSubgraph:CRITIC] Triggered self-healing diagnosis for error: {state.get('error_log')}"
    )
    res = await reflection_agent.reflect(state, config)
    patch: Dict[str, Any] = dict(res or {})

    # 保证重试计数自增
    if "retry_count" not in patch:
        patch["retry_count"] = state.get("retry_count", 0) + 1

    # 记录执行足迹
    execution_trace = list(state.get("execution_trace") or [])
    execution_trace.append(f"critic_reflect_v{patch.get('retry_count')}")
    patch["execution_trace"] = execution_trace

    return patch


# ── 3. 子图编译工厂 ───────────────────────────────────────────

def build_execution_subgraph(max_retries: int = 2) -> CompiledStateGraph:
    """
    [Matt Pocock Deep Module / Subgraph Assembler]
    组装并编译数据执行与自愈微循环子图。

    拓扑图：
      ENTRY -> CODER -> GATE -[通过/熔断]-> END
                        |
                     [失败自愈]
                        v
                      CRITIC -> CODER
    """
    wf = StateGraph(ExecutionSubState)

    wf.add_node("CODER", coder_step)
    wf.add_node("GATE", gate_step)
    wf.add_node("CRITIC", critic_step)

    wf.set_entry_point("CODER")
    wf.add_edge("CODER", "GATE")

    def _route_gate_post(state: ExecutionSubState) -> str:
        # 1. 成功直通路径
        if state.get("sql_validated") is True and not state.get("error_log"):
            return "END"

        # 2. 逃生舱熔断机制 (Escape Hatch)
        curr_retries = state.get("retry_count", 0)
        curr_max = state.get("max_retries", max_retries)
        if curr_retries >= curr_max:
            logger.warning(
                f"[ExecutionSubgraph] Escape hatch triggered: retry_count={curr_retries} >= max_retries={curr_max}. Exiting subgraph."
            )
            return "END"

        # 3. 自愈回路
        return "CRITIC"

    wf.add_conditional_edges(
        "GATE",
        _route_gate_post,
        {
            "END": END,
            "CRITIC": "CRITIC",
        },
    )
    wf.add_edge("CRITIC", "CODER")

    return wf.compile()


# 默认单例编译实例 (供模块级及测试 patch 使用)
compiled_execution_subgraph: CompiledStateGraph = build_execution_subgraph(max_retries=2)


# ── 4. 父图门面适配器节点 (Clean Seam Facade) ─────────────────

async def execution_engine_node(
    state: Dict[str, Any], 
    config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """
    [Matt Pocock Deep Module / Clean Seam]
    父图接入子图的门面适配器节点 (Facade Node)。

    核心职责：
    1. 输入隔离投影：将父图臃肿的 AuditState 精简收敛为子图入参契约；
    2. 子图透明调用：委托给 compiled_execution_subgraph 完成执行与自愈；
    3. 输出收敛接缝：严格过滤子图内部私有字段 (sql_history, internal_critic_log 等)，
       仅向父图合并核心交付物 (sql_query, raw_data, sql_validated, execution_trace)。
    """
    # 1. 投影构建子图输入状态
    sub_input: ExecutionSubState = {
        "tasks": state.get("tasks") or [],
        "methodology": state.get("methodology") or "",
        "metadata": state.get("metadata") or {},
        "session_id": state.get("session_id") or "",
        "messages": state.get("messages") or [],
        "retry_count": 0,
        "max_retries": 2,
        "sql_history": [],
        "execution_trace": list(state.get("execution_trace") or []),
        "evidence_row_count": int(state.get("evidence_row_count") or 0),
    }

    # 2. 调用已编译子图
    sub_res = await compiled_execution_subgraph.ainvoke(sub_input, config)

    # 3. 严格输出投影过滤 (Information Hiding)
    # 仅允许暴露给父图的核心交付物字段
    PARENT_FACING_KEYS = {
        "sql_query",
        "final_sql",
        "raw_data",
        "evidence_row_count",
        "sql_validated",
        "execution_trace",
        "temp_table",
        "is_awaiting_human",
        "error_log",
    }

    output_patch: Dict[str, Any] = {}
    for key in PARENT_FACING_KEYS:
        if key in sub_res and sub_res[key] is not None:
            output_patch[key] = sub_res[key]

    # 保证 sql_query 与 final_sql 的向后兼容互通
    if "sql_query" not in output_patch and "final_sql" in output_patch:
        output_patch["sql_query"] = output_patch["final_sql"]
    elif "final_sql" not in output_patch and "sql_query" in output_patch:
        output_patch["final_sql"] = output_patch["sql_query"]

    # 保证核心断言键存在 (即使为初始状态)
    for required_key in ["sql_query", "raw_data", "sql_validated", "execution_trace"]:
        if required_key not in output_patch:
            output_patch[required_key] = sub_res.get(required_key)

    return output_patch
