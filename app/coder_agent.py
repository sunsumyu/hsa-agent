"""
app/coder_agent.py
==================
[V150.0] 审计执行智能体 (Coder Agent)

负责：
1. 动态工具绑定：结合权限管理 (PermissionManager) 下发工具。
2. 物理执行循环：处理工具调用、结果脱敏与异常捕获。
3. 质量门控：集成 SQL Linter、Sequence 验证与数值异常监测。
"""

import json
import asyncio
import hashlib
import time
from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from app.core.llm_provider import llm_provider
from app.core.registry import skill_registry
from app.core.permission_manager import permission_manager
from app.semantic_memory import cognitive_memory_manager
from app.schema_injector import schema_injector
from app.neo4j_manager import neo4j_manager
from app.prompts import CODER_PROMPT
from app.sql_validator import sql_validator
from app.booster import booster
from app.structured_tracer import StructuredTracer

class AuditCoderAgent:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def execute(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        """执行审计代码生成与物理查询 [V171.2]"""
        # 初始化结构化追踪器
        tracer = StructuredTracer(
            session_id=state.get("session_id", "default"),
            on_event_cb=getattr(config, "on_trace_update", None)
        )
        
        retry = state.get("retry_count", 0)
        if retry >= self.max_retries:
            return {"error_log": "REACHED_MAX_RETRIES"}

        # 1. 动态权限与工具准备
        user_id = (state.get("metadata") or {}).get("user_id", "default_senior")
        all_tools = skill_registry.get_all_skills()
        tools = permission_manager.filter_skills(user_id, all_tools)

        # 2. 上下文准备
        tasks_list = state.get("tasks", [])
        mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), "\n".join(tasks_list))
        
        user_messages = [m for m in state.get("messages", []) if getattr(m, "type", "") == "human"]
        user_q = " ".join(str(m.content) for m in user_messages)[:200]
        schema_hint = schema_injector.inject(user_question=f"{user_q} {' '.join(tasks_list)}")

        prompt = CODER_PROMPT.format_messages(
            original_question=user_q,
            messages=state["messages"], 
            ontology=neo4j_manager.get_ontology(),
            schema_info=schema_hint,
            methodology=state.get("methodology", ""),
            tasks="\n".join(tasks_list), 
            experiences=mem_context
        )

        # 3. 执行 LLM 思考逻辑 (生成 SQL)
        with tracer.span("CODER_REASONING", node="CODER") as span:
            response = await llm_provider.chat(
                role="coder",
                messages=prompt,
                config=config,
                state=state,
                tools=tools
            )
            
            if not getattr(response, "tool_calls", None):
                 span.set_result("未触发工具调用，直接回复")
                 return {"messages": [response], "error_log": None, "execution_trace": tracer.to_legacy_list()}
            
            span.set_result(f"生成了 {len(response.tool_calls)} 个工具调用指令")

        # 4. 物理工具执行 (SQL 执行)
        with tracer.span("SQL_EXECUTION", node="CODER") as span:
            results = await self._invoke_tools_parallel(response.tool_calls, tools)
            span.set_result(f"物理执行完成，获取 {len(results)} 组结果集")
        
        # 5. 结果聚合与处理 (迁移自原 sqlexec_node)
        processed = self._process_tool_results(results, state)
        
        # 6. 质量门控 (Linter & Booster)
        with tracer.span("QUALITY_GATE", node="CODER") as span:
            gate_error = self._run_quality_gates(processed["sql_query"], processed["methodology"], processed["raw_data"], processed["execution_trace"])
            if gate_error:
                span.fail(gate_error)
                return {
                    "error_log": gate_error,
                    "sql_query": processed["sql_query"],
                    "messages": [response] + processed["tool_msgs"],
                    "retry_count": retry + 1,
                    "execution_trace": tracer.to_legacy_list()
                }
            span.set_result("逻辑与数值对齐校验通过")

        return {
            "raw_data": processed["raw_data"],
            "sql_query": processed["sql_query"],
            "sql_history": processed["sql_history"], # [V178.9] 证据链持久化
            "methodology": processed["methodology"],
            "messages": [response] + processed["tool_msgs"],
            "retry_count": retry + 1,
            "sql_validated": True,
            "error_log": None,
            "execution_trace": tracer.to_legacy_list(),
            "temp_table": state.get("temp_table")
        }

    async def _invoke_tools_parallel(self, tool_calls, tools):
        async def _single_call(tc):
            t_instance = next((t for t in tools if t.name == tc["name"]), None)
            if not t_instance: return tc, {"status": "ERROR", "error_message": f"Unknown tool: {tc['name']}"}
            try:
                res = await t_instance.ainvoke(tc["args"])
                return tc, res
            except Exception as e:
                return tc, {"status": "ERROR", "error_message": str(e)}

        tasks = [_single_call(tc) for tc in tool_calls]
        return await asyncio.gather(*tasks)

    def _process_tool_results(self, results, state):
        tool_msgs = []
        raw_data_list = []
        sql_logics = []
        methodologies = []
        tool_traces = []
        has_error = False
        error_msg = ""
        
        for t_call, res in results:
            # 生成 Trace ID
            trace_id = hashlib.sha256(f"{t_call['name']}_{time.time()}".encode()).hexdigest()[:8].upper()
            
            tool_msg = ToolMessage(content=str(res)[:2000], tool_call_id=t_call["id"])
            tool_msgs.append(tool_msg)
            
            if isinstance(res, dict):
                if "sql_logic" in res: sql_logics.append(res["sql_logic"])
                if "methodology" in res: methodologies.append(res["methodology"])
                if "trace_hint" in res: tool_traces.append(f"[{trace_id}] {res['trace_hint']}")
                if res.get("status") == "ERROR":
                    has_error = True
                    error_msg = res.get("error_message") or "Tool execution failed"
                
                # 证据链提取
                if "records_sample" in res: raw_data_list.append(str(res["records_sample"]))
                if "raw_evidence" in res: raw_data_list.append(str(res["raw_evidence"]))
        
        return {
            "tool_msgs": tool_msgs,
            "raw_data": "\n---\n".join(raw_data_list),
            "sql_query": sql_logics[-1] if sql_logics else "",
            "sql_history": sql_logics, # [V178.9] 证据链全量化
            "methodology": "\n\n".join(methodologies),
            "execution_trace": state.get("execution_trace", []) + tool_traces,
            "has_error": has_error,
            "error_msg": error_msg
        }

    def _run_quality_gates(self, sql, methodology, raw_data, trace):
        # 1. SQL Linter
        is_ok, linter_msg = sql_validator.agentic_linter(sql)
        if not is_ok: return f"【SQL 逻辑审查拦截】{linter_msg}"
        
        # 2. 数值异常监测
        rows = booster.parse_table_to_rows(raw_data)
        anomaly_msg = booster.detect_anomalous_consistency(rows)
        if anomaly_msg: return f"【数值异常拦截】{anomaly_msg}"
        
        return None

coder_agent = AuditCoderAgent()
