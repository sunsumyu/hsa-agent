import re

with open("e:/chain/hsa-agent-python/app/agent_graph.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add skill imports
content = content.replace(
    "from app.tools import execute_audit_sql, get_table_schema, list_tables, search_expert_knowledge",
    "from app.tools import execute_audit_sql, get_table_schema, list_tables, search_expert_knowledge\nfrom app.skills import MedicalSchemaSkill, RuleExecutionSkill, SQLSafeExecutionSkill"
)

# 2. Rewrite sqlexec_node
# We will match the entire sqlexec_node
sqlexec_pattern = re.compile(r"async def sqlexec_node.*?async def auditor_node", re.DOTALL)

new_sqlexec = """async def sqlexec_node(state: AuditState, config: RunnableConfig):
    \"\"\"
    [工业级 Skills 节点] 完全基于 Tool Calling 调用独立封装的 Skills。
    \"\"\"
    retry = state.get("retry_count", 0)
    if retry >= MAX_RETRIES:
        logger.error(f"🛑 [SQLEXEC] 达到重试上限，强制熔断并汇报失败。")
        return {
            "raw_data": "【审计异常】由于系统未能生成有效逻辑，任务已强制终止。",
            "sql_validated": True,
            "error_log": "REACHED_MAX_RETRIES"
        }

    # 优先走 Fast Route
    fast_route_id = (state.get("metadata") or {}).get("fast_route_id")
    if fast_route_id:
        logger.success(f"🚀 [FAST_EXEC] Fast Route 命中，直接执行 Skill")
        try:
            skill = RuleExecutionSkill()
            res = await skill._arun(fast_route_id)
            trace = _append_trace(state, res.get("trace_hint", ""))
            
            import json as _j
            import datetime as _dt
            from decimal import Decimal as _Dec

            class _AuditEncoder(_j.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, (_dt.datetime, _dt.date)): return obj.isoformat()
                    if isinstance(obj, _Dec): return float(obj)
                    return super().default(obj)
            
            raw_evidence = res.get("raw_evidence", [])
            result_str = _j.dumps(raw_evidence, ensure_ascii=False, cls=_AuditEncoder) if isinstance(raw_evidence, list) else str(raw_evidence)
            
            return {
                "raw_data": result_str,
                "sql_query": f"-- FastRoute: {fast_route_id}",
                "sql_validated": True,
                "error_log": None,
                "execution_trace": trace,
            }
        except Exception as e:
            logger.warning(f"⚠️ [FAST_EXEC] 执行异常: {e}")
            state.get("metadata", {}).pop("fast_route_id", None)

    logger.info(f">>> [SKILLS] LLM 智能调度 Skills... (尝试 {retry + 1}/3)")
    llm, actual_model = model_manager.get_llm_by_role("coder", retry_count=retry, config=config)
    
    tools = [MedicalSchemaSkill(), RuleExecutionSkill(), SQLSafeExecutionSkill()]
    llm_with_tools = llm.bind_tools(tools)
    
    tasks_list = state.get("tasks", [])
    mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), "\\n".join(tasks_list))
    
    prompt_template = get_langfuse_prompt("coder-sql-expert-v1", fallback=CODER_PROMPT)
    # 不再全量注入 schema
    prompt = prompt_template.format_messages(
        messages=state["messages"], schema_info="请使用 lookup_medical_schema 技能按需查询字段",
        tasks="\\n".join(tasks_list), experiences=mem_context, semantic_dict=""
    )
    
    if retry > 0 and state.get("error_log"):
        prompt.append(HumanMessage(content=f"上一轮执行失败，原因：{state['error_log']}\\n请修正参数并重新调用工具。"))
    
    obs_config = build_obs_config(config, "sqlexec", state)
    response = await llm_with_tools.ainvoke(prompt, config=obs_config)
    _record_usage_with_budget("coder", response, actual_model, prompt=prompt)
    
    if getattr(response, "tool_calls", None):
        async def invoke_tool(t_call):
            t_instance = next((t for t in tools if t.name == t_call["name"]), None)
            if t_instance:
                res = await t_instance.ainvoke(t_call["args"])
                return t_call, res
            return t_call, None

        eval_tasks = [invoke_tool(tc) for tc in response.tool_calls]
        results = await asyncio.gather(*eval_tasks)
        
        tool_msgs = []
        raw_data_list = []
        tool_traces = []
        has_error = False
        error_msg = ""
        
        for t_call, res in results:
            if res is not None:
                tool_msg = ToolMessage(content=str(res), tool_call_id=t_call["id"])
                tool_msgs.append(tool_msg)
                
                if isinstance(res, dict):
                    if res.get("status") == "ERROR" or "error" in res:
                        has_error = True
                        error_msg = res.get("error_message") or res.get("error")
                    else:
                        if "records_sample" in res:
                            raw_data_list.append(str(res["records_sample"]))
                        if "raw_evidence" in res:
                            raw_data_list.append(str(res["raw_evidence"]))
                        if "trace_hint" in res:
                            tool_traces.append(res["trace_hint"])
                else:
                    raw_data_list.append(str(res))

        trace = list(state.get("execution_trace") or [])
        for hint in tool_traces:
            trace = _append_trace({"execution_trace": trace}, hint)

        if has_error:
            logger.warning(f"Skill 报错: {error_msg}")
            return {
                "error_log": error_msg,
                "messages": [response] + tool_msgs,
                "retry_count": retry + 1,
                "execution_trace": trace
            }

        combined_raw = "\\n---\\n".join(raw_data_list)
        return {
            "raw_data": combined_raw,
            "messages": [response] + tool_msgs,
            "retry_count": retry + 1,
            "sql_validated": True,
            "error_log": None,
            "execution_trace": trace
        }
    
    # 无工具调用，尝试解析内容
    return {
        "error_log": "Agent did not output a tool call.",
        "messages": [response],
        "retry_count": retry + 1
    }

async def auditor_node"""

content = sqlexec_pattern.sub(new_sqlexec, content)

# 3. Modify the graph topology and remove auditor_node
auditor_pattern = re.compile(r"async def auditor_node.*?async def reporter_node", re.DOTALL)
content = auditor_pattern.sub("async def reporter_node", content)

# 4. Modify build_graph
build_graph_pattern = re.compile(r"def build_graph\(\):.*?return workflow\.compile\(\)", re.DOTALL)
new_build_graph = """def build_graph():
    \"\"\"
    [工业级 Skills 拓扑] 严格的线性工作流
    PLANNER → SKILLS_EXEC(原SQLEXEC) ↺(限次重试) → CONSOLIDATOR → REPORTER → END
    \"\"\"
    workflow = StateGraph(AuditState)
    workflow.add_node("PLANNER", planner_node)
    workflow.add_node("SQLEXEC", sqlexec_node)  # 我们保留了名字以兼容旧代码
    workflow.add_node("REPORTER", reporter_node)
    workflow.add_node("CONSOLIDATOR", consolidator_node)

    workflow.set_entry_point("PLANNER")
    workflow.add_edge("PLANNER", "SQLEXEC")
    
    def route_post_exec(state: AuditState) -> str:
        if state.get("error_log") and state.get("retry_count", 0) < MAX_RETRIES:
            return "SQLEXEC"  # 发生错误则原节点重试
        return "CONSOLIDATOR" # 成功直接进入整合
        
    workflow.add_conditional_edges(
        "SQLEXEC", route_post_exec,
        {"SQLEXEC": "SQLEXEC", "CONSOLIDATOR": "CONSOLIDATOR"}
    )
    workflow.add_edge("CONSOLIDATOR", "REPORTER")
    workflow.add_edge("REPORTER", END)
    return workflow.compile()"""

content = build_graph_pattern.sub(new_build_graph, content)

# Save
with open("e:/chain/hsa-agent-python/app/agent_graph.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Refactoring complete.")
