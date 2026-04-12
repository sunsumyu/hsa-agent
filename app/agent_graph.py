import os
import operator
import json
from typing import Annotated, Sequence, TypedDict, List, Union, Dict, Any
from loguru import logger

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from app.tools import execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge
from app.model_manager import model_manager
from app.usage_tracker import usage_tracker
from app.compressor import compress_findings_to_summary
from app.prompts import (
    SUPERVISOR_PROMPT, 
    DATA_EXPERT_PROMPT, 
    AUDITOR_PROMPT, 
    FINANCIAL_PROMPT, 
    REPORTER_PROMPT
)

# 2. 线索过滤与合并逻辑 (V4.1.2 Physical Filtering)
def merge_findings(left: List[str], right: List[str]) -> List[str]:
    """
    自定义 Reducer：实现物理级去燥。
    1. 处理 ⟦OVERWRITE⟧ 指令。
    2. 物理删除技术底噪（沙箱报错、架构警告等）。
    """
    # [V4.1.5] 线索库精准降噪逻辑
    NOISE_PATTERNS = [
        r"SQL Sandbox:?\s*", r"only SELECT/WITH/EXPLAIN allowed",
        r"仅允许只读审计", r"基于审计安全协议", r"禁止执行", r"SELECT, WITH, EXPLAIN",
        r"Key 'title' is not supported", r"Key 'default' is not supported",
        r"Result: Error:", r"查询?失败:?\s*", r"ClickHouse 执行失败:?\s*"
    ]
    import re
    def sanitize(f: str) -> str:
        s = str(f)
        for p in NOISE_PATTERNS:
            s = re.sub(p, "", s, flags=re.IGNORECASE)
        return s.strip()

    if right and isinstance(right[0], str) and right[0].startswith("⟦OVERWRITE⟧"):
        content = right[0].replace("⟦OVERWRITE⟧", "")
        sanitized = sanitize(content)
        # 如果清洗后变成了空字符串或无意义符号，则不加入线索库
        return [sanitized] if len(sanitized) > 5 else []
    
    incoming = []
    for f in (right or []):
        sanitized = sanitize(f)
        if len(sanitized) > 5:
            incoming.append(sanitized)
    return (left or []) + incoming

# 2. 消息流管理 (V4.6.0 History Overwrite)
def merge_messages(left: Sequence[BaseMessage], right: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    """
    智能消息合并器：支持 ⟦OVERWRITE⟧ 物理截断历史信息，防止上下文爆炸。
    """
    if right and len(right) > 0:
        # 检查是否包含覆盖指令 (通常检查第一条新消息的内容)
        first_msg = right[0]
        if hasattr(first_msg, "content") and isinstance(first_msg.content, str) and "⟦OVERWRITE⟧" in first_msg.content:
            logger.warning(">>> [历史剪枝] 检测到物理覆盖指令，正在重置上下文空间。")
            # 移除指令标记并返回全新列表
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
            new_content = first_msg.content.replace("⟦OVERWRITE⟧", "").strip()
            
            new_first = None
            if isinstance(first_msg, HumanMessage):
                new_first = HumanMessage(content=new_content)
            elif isinstance(first_msg, AIMessage):
                new_first = AIMessage(content=new_content)
            elif isinstance(first_msg, SystemMessage):
                # 强制降级，禁止重写为 SystemMessage
                new_first = AIMessage(content=new_content)
            else:
                return right
                
            merged_result = [new_first] + list(right)[1:]
        else:
            merged_result = (left or []) + list(right)
    else:
        merged_result = left or []
        
    # [V4.6.4] 兼容性自愈 (State Migration):
    # 扫描并清理历史数据库遗留的 SystemMessage (大模型 API 严格约束 SystemMessage 只能在首位)
    from langchain_core.messages import AIMessage, SystemMessage
    sanitized_messages = []
    for m in merged_result:
        if isinstance(m, SystemMessage):
            sanitized_messages.append(AIMessage(content=f"[{m.content}]"))
        else:
            sanitized_messages.append(m)
            
    return sanitized_messages

class AuditState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], merge_messages] 
    findings: Annotated[List[str], merge_findings] 
    next_expert: str
    model_id: str
    retry_count: Annotated[int, lambda x, y: (x or 0) + (y or 0)]
    step_counter: Annotated[int, lambda x, y: (x or 0) + (y or 0)] 
    expert_history: Annotated[List[str], operator.add] 
    tool_call_history: Annotated[Dict[str, int], lambda x, y: {**x, **y}] # 新增：工具调用次数统计

# 2. 工具集隔离
# [V4.1.6] 恢复物理视野：既然降噪已闭闭环，恢复 list_tables 以提升数据发现效率
DATA_TOOLS = [execute_audit_sql, get_table_schema, list_tables]
AUDIT_TOOLS = [search_expert_knowledge]
FINANCIAL_TOOLS = [calculator]

# 3. 辅助功能
def record_llm_usage(response: AIMessage, model_id: str):
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        meta = response.usage_metadata
        usage_tracker.record_usage(model_id, meta.get("input_tokens", 0), meta.get("output_tokens", 0))

def get_model(model_id: str, require_tools: bool = True):
    return model_manager.get_adaptive_llm(model_id=model_id, require_tools=require_tools)

# 4. 核心节点实现

def supervisor_node(state: AuditState):
    """
    智能总控节点 (Supervisor):
    负责任务分解与路由决策。
    """
    retry_count = state.get("retry_count", 0)
    step_counter = state.get("step_counter", 0)
    
    # [V4.2.2] 强化型断路器：针对死循环的硬性干预
    if retry_count > 15 or step_counter > 50:
        logger.error(f"检测到深度推演 (重试:{retry_count}/总步数:{step_counter})，指挥官强行指派 REPORTER 总结。")
        return {"next_expert": "REPORTER", "retry_count": retry_count, "step_counter": 1}

    llm, resolved_id = get_model(state.get("model_id", "qwen-max"), require_tools=False)
    
    # 汇总 Findings 供总控参考
    findings_str = "\n".join([f"- {f}" for f in state.get("findings", [])]) or "尚无发现。"
    
    from langchain_core.messages import SystemMessage
    history_msgs = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
    
    chain = SUPERVISOR_PROMPT | llm
    response = chain.invoke({"messages": history_msgs, "findings": findings_str})
    record_llm_usage(response, resolved_id)
    
    # 健壮性提取：处理可能返回的 list 格式 content
    content = response.content
    if isinstance(content, list):
        content = " ".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
    
    next_expert = content.strip().upper()
    # 移除可能存在的引号或多余字符
    next_expert = "".join(filter(str.isalnum, next_expert)).replace(" ", "")
    
    if "DATAEXPERT" in next_expert: next_expert = "DATA_EXPERT"
    elif "AUDITOR" in next_expert: next_expert = "AUDITOR"
    elif "FINANCIALEXPERT" in next_expert: next_expert = "FINANCIAL_EXPERT"
    elif "REPORTER" in next_expert: next_expert = "REPORTER"
    else: next_expert = "DATA_EXPERT"
        
    # [V4.6.0] 循环检测：防止同一工具由于参数不变而死循环
    tool_call_history = state.get("tool_call_history", {})
    # 简单的外部监控：如果状态中检测到异常的工具足迹
    
    logger.warning(f"!!! [指挥官决策] 路由至节点: {next_expert} (步数: {step_counter}) !!!")
    return {
        "next_expert": next_expert, 
        "retry_count": state.get("retry_count", 0),
        "step_counter": 1, 
        "expert_history": [next_expert], 
        "findings": state.get("findings", []),
        "tool_call_history": tool_call_history
    }

def pruning_node(state: AuditState):
    """
    [V4.6.0] 物理剪枝节点：当上下文消息超过 15 条时，强制保留首尾，其余压缩。
    """
    messages = list(state.get("messages", []))
    if len(messages) <= 15:
        return {"messages": []} # 无需剪枝
    
    logger.warning(f">>> [系统内燃机] 正在对 {len(messages)} 条上下文进行物理脱水...")
    # 保留第一条 (User Prompt) 和最后 5 条 (Current Context)
    first = messages[0]
    tail = messages[-5:]
    
    # [V4.6.3] 必须使用 AIMessage 承载摘要，防止大模型接口检测报错 "SystemMessage at position 1"
    from langchain_core.messages import AIMessage
    summary_msg = AIMessage(content=f"⟦OVERWRITE⟧ [系统摘要]: 已压缩早期推演过程。当前已知事实: {len(state.get('findings', []))} 条线索。")
    
    return {"messages": [summary_msg, first] + tail}

def data_expert_node(state: AuditState):
    llm, model_id = get_model(state.get("model_id", "qwen-max"))
    
    # 注入当前压缩后的线索摘要供专家参考
    findings_str = "\n".join([f"- {f}" for f in state.get("findings", [])]) or "尚无从前发现。"
    
    # [V4.6.5] 协议硬隔离：过滤所有历史记录中的 SystemMessage，防止叠加导致 Pos 1 报错
    from langchain_core.messages import SystemMessage
    history_msgs = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
    
    chain = DATA_EXPERT_PROMPT | llm.bind_tools(DATA_TOOLS)
    response = chain.invoke({"messages": history_msgs, "findings": findings_str})
    record_llm_usage(response, model_id)
    
    return {"messages": [response], "retry_count": state.get("retry_count", 0)}

def auditor_node(state: AuditState):
    llm, model_id = get_model(state.get("model_id", "qwen-max"))
    
    chain = AUDITOR_PROMPT | llm.bind_tools(AUDIT_TOOLS)
    response = chain.invoke(state)
    record_llm_usage(response, model_id)
    return {"messages": [response], "retry_count": state.get("retry_count", 0)}

def compressor_node(state: AuditState):
    """
    线索压缩节点 (V4.0):
    每轮推演后，利用高级语义模型对庞杂的线索进行提纯。
    """
    raw_findings = state.get("findings", [])
    if not raw_findings:
        return {"findings": []}
        
    summary = compress_findings_to_summary(raw_findings)
    # 使用 ⟦OVERWRITE⟧ 符号通知 Reducer 替换历史记录
    return {"findings": ["⟦OVERWRITE⟧" + summary]}

def financial_expert_node(state: AuditState):
    llm, model_id = get_model(state.get("model_id", "qwen-max"))
    
    chain = FINANCIAL_PROMPT | llm.bind_tools(FINANCIAL_TOOLS)
    response = chain.invoke(state)
    record_llm_usage(response, model_id)
    return {"messages": [response], "retry_count": state.get("retry_count", 0)}

def reporter_node(state: AuditState):
    llm, model_id = get_model(state.get("model_id", "qwen-max"), require_tools=False)
    
    # 汇总 Findings 供报告专家参考 (列表级预处理，防止列表过长导致序列化异常)
    raw_findings = state.get("findings", [])
    if len(raw_findings) > 20:
        logger.info(f"REPORTER: 证据点过多 ({len(raw_findings)})，执行头尾智能采样...")
        raw_findings = raw_findings[:15] + ["...[此处由于证据链过长，已截断部分明细数据，重点请见后文总结]..."] + raw_findings[-5:]
        
    findings_str = "\n".join([f"- {f}" for f in raw_findings]) or "尚无明确发现。"
    
    # [V4.6.2] 源头物理隔离：绝不让总结模型看到真实的物理表名
    import re
    patterns_to_mask = [r'fqz_[a-zA-Z0-9_]+', r't_audit_[a-zA-Z0-9_]+', r'medins_[a-zA-Z0-9_]+']
    for p in patterns_to_mask:
        findings_str = re.sub(p, '【业务数据表】', findings_str, flags=re.IGNORECASE)
    
    # 限制历史消息长度，防止 Context Bloat 导致接口挂起，并执行 V4.1.3 物理脱敏
    messages = state.get("messages", [])
    trimmed_messages = messages[:1] + messages[-10:] if len(messages) > 11 else messages
    
    # [V4.1.5] 对话历史精准降噪：保留自愈建议，剥离技术前缀
    NOISE_PATTERNS = [
        r"SQL Sandbox:?\s*", r"only SELECT/WITH/EXPLAIN allowed",
        r"仅允许只读审计", r"基于审计安全协议", r"禁止执行", r"SELECT, WITH, EXPLAIN",
        r"Key 'title' is not supported", r"Key 'default' is not supported",
        r"查询?失败:?\s*", r"ClickHouse 执行失败:?\s*"
    ]
    import re
    from langchain_core.messages import ToolMessage
    for msg in trimmed_messages:
        if isinstance(msg, ToolMessage):
            content_str = str(msg.content)
            for p in NOISE_PATTERNS:
                content_str = re.sub(p, "", content_str, flags=re.IGNORECASE)
            # 物理标记业务化
            if any(kw in content_str for kw in ["Unknown function", "Unknown identifier", "Unknown table", "Table", "not exist"]):
                content_str = f"[业务匹配调试中] {content_str}"
            msg.content = content_str
    
    # [V4.6.5] 协议对齐：REPORTER_PROMPT 已自带 System 角色，此处必须物理隔离历史中的 System 消息
    final_messages = [m for m in trimmed_messages if not isinstance(m, SystemMessage)]
    
    prompt_msgs = REPORTER_PROMPT.format_messages(messages=final_messages, findings=findings_str)
    
    logger.info(f"!!! REPORTER: 准备提交总结请求 (发现物长度: {len(findings_str)}) !!!")
    try:
        response = llm.invoke(prompt_msgs)
        logger.info("!!! REPORTER: 总结请求已响应成功 !!!")
    except Exception as e:
        logger.error(f"REPORTER 节点逻辑崩溃: {e}")
        # 构造一个保底的 AI 消息
        from langchain_core.messages import AIMessage
        response = AIMessage(content=f"由于技术原因未能生成完整报告。初步发现如下：\n{findings_str[:1000]}")

    # 鲁棒性检查：确保 content 是字符串 (某些模型可能返回 list/dict)
    content = response.content
    if isinstance(content, list):
        content = " ".join([str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content])
    
    response.content = content

    if not content or len(content) < 5:
        logger.warning("REPORTER 返回结论过短或为空，启动格式化保底机制。")
        # 兜底也必须符合 Audit Card V2 降级协议
        fallback_msg = (
            "### 🚩 阶段性审计评估 (自动生成)\n"
            f"- **探定范围**: 已探索物理库表，长度 {len(findings_str)} 字符。\n"
            "- **受阻现状**: 分析器未能针对物理事实给出最终结论，或未发现显著异常单据。\n"
            "- **下一步建议**: 建议复核物理表约束，或通过专家系统重新构造目标维度。\n"
        )
        response.content = fallback_msg
        
    return {"messages": [response], "retry_count": 0}

def tool_node(state: AuditState):
    """手动分发工具调用，带简单的重试计数逻辑。"""
    messages = state["messages"]
    last_message = messages[-1]
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": []}
        
    results = []
    tool_map = {t.name: t for t in (DATA_TOOLS + AUDIT_TOOLS + FINANCIAL_TOOLS)}
    
    # [V4.6.0] 工具调用频率统计：用于死循环检测器
    tool_call_history = state.get("tool_call_history", {})
    new_findings = []
    
    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        args = tool_call["args"]
        call_id = tool_call["id"]
        
        # 记录足迹：(工具名+关键参数)
        param_slug = f"{name}:{str(args.get('table_name', ''))}:{str(args.get('sql', ''))[:20]}"
        tool_call_history[param_slug] = tool_call_history.get(param_slug, 0) + 1
        
        logger.info(f"执行工具: {name} (此参数第 {tool_call_history[param_slug]} 次执行)...")
        tool = tool_map.get(name)
        if tool:
            try:
                res = tool.invoke(args)
                results.append(ToolMessage(content=str(res), tool_call_id=call_id))
                # 状态裁剪：如果结果有价值，存入 findings (包含 Schema 发现)
                if name in ["execute_audit_sql", "search_expert_knowledge", "calculator", "get_table_schema", "list_tables"]:
                    new_findings.append(f"[{name}] Result: {str(res)[:300]}")
            except Exception as e:
                results.append(ToolMessage(content=f"Error: {str(e)}", tool_call_id=call_id))
        else:
            results.append(ToolMessage(content=f"Error: Tool {name} not found", tool_call_id=call_id))
            
    return {
        "messages": results, 
        "findings": new_findings, 
        "retry_count": state.get("retry_count", 0) + 1,
        "tool_call_history": tool_call_history
    }

# 5. 路由逻辑

def router(state: AuditState):
    if state["messages"][-1].tool_calls:
        if state.get("retry_count", 0) > 20: # 全局最大保护
            logger.error("!!! 触发最大重试限制，强行切断循环 !!!")
            return "compressor"
        return "tools"
    return "compressor"

# 6. 构建图

workflow = StateGraph(AuditState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("data_expert", data_expert_node)
workflow.add_node("auditor", auditor_node)
workflow.add_node("financial_expert", financial_expert_node)
workflow.add_node("reporter", reporter_node)
workflow.add_node("compressor", compressor_node)
workflow.add_node("tools", tool_node)

workflow.add_node("pruning", pruning_node)

workflow.set_entry_point("supervisor")

# 总控分发
workflow.add_conditional_edges("supervisor", lambda x: x["next_expert"].lower(), {
    "data_expert": "data_expert",
    "auditor": "auditor",
    "financial_expert": "financial_expert",
    "reporter": "reporter"
})

# 专家返回压缩层或执行工具
workflow.add_conditional_edges("data_expert", router, {"tools": "tools", "compressor": "compressor"})
workflow.add_conditional_edges("auditor", router, {"tools": "tools", "compressor": "compressor"})
workflow.add_conditional_edges("financial_expert", router, {"tools": "tools", "compressor": "compressor"})

# 所有数据终点在进入总控前必须经过压缩与裁剪
workflow.add_edge("tools", "compressor")
workflow.add_edge("compressor", "pruning")
workflow.add_edge("pruning", "supervisor")
workflow.add_edge("reporter", END)

def get_graph_executor(checkpointer=None, model_id: str = None):
    app = workflow.compile(checkpointer=checkpointer)
    
    # [V4.5.7] 算力并网对齐：如果前端传入为空 (Auto)，则解析注册表中优先级最高的服务名
    if not model_id or model_id == "auto":
        model_list = model_manager.get_model_list()
        if model_list:
            # 按优先级降序排序，取最高优先级
            sorted_m = sorted(model_list, key=lambda x: x.get("priority", 99))
            model_id = sorted_m[0]["id"]
        else:
            model_id = "qwen-turbo" # 终极兜底
            
    return app, model_id
