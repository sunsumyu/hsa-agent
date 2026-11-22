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
import re
from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, BaseMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.llm_provider import llm_provider
from app.core.registry import skill_registry
from app.core.permission_manager import permission_manager
from app.skills.schema.schema_injector import schema_injector
from app.skills.sql.sql_validator import sql_validator
from app.core.booster import booster
from app.core.structured_tracer import StructuredTracer

from app.skills.security.probe_guard import is_probe_query
from app.agents.coder_quality_guard import (
    check_pre_execution_gate,
    check_post_execution_gate,
    run_quality_linter,
)
from app.agents.coder_prompt_assembler import assemble_coder_prompt
from app.agents.fast_route_executor import execute_fast_route_bypass
from app.agents.coder_inference_coordinator import coordinate_coder_inference


class AuditCoderAgent:
    def __init__(self, max_retries: Optional[int] = None):
        self._max_retries = max_retries

    @property
    def max_retries(self) -> int:
        from app.core.config import settings
        return self._max_retries if self._max_retries is not None else settings.max_agent_retries

    def _is_probe_query(self, sql: str) -> bool:
        """Delegate to extracted probe_guard module for backward compat."""
        return is_probe_query(sql)

    async def execute(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        """执行审计代码生成与物理查询 [V171.2]"""
        # 初始化结构化追踪器
        tracer = StructuredTracer(
            session_id=state.get("session_id", "default"),
            on_event_cb=getattr(config, "on_trace_update", None)
        )
        
        retry = state.get("retry_count", 0)
        if retry >= self.max_retries:
            preserved_raw_data = state.get("raw_data", "")
            has_valid_execution = state.get("sql_validated", False) and bool(preserved_raw_data)
            history_sql = state.get("sql_history", [])
            core_sql = state.get("sql_query", "") or resolve_core_audit_sql(history_sql, is_probe_fn=self._is_probe_query)


            if has_valid_execution:
                logger.info("✨ [Coder State Safeguard] 达到最大重试次数，但前序已成功物理取证，保全成果完成交付")
                return {
                    "error_log": None,
                    "sql_validated": True,
                    "sql_query": core_sql,
                    "sql_history": history_sql,
                    "raw_data": preserved_raw_data,
                    "retry_count": retry,
                    "execution_trace": tracer.to_legacy_list()
                }

            return {
                "error_log": "REACHED_MAX_RETRIES",
                "retry_count": retry + 1
            }

        # 计算是否出现了重复 SQL 的执行
        sql_history = state.get("sql_history", [])
        has_duplicate_sql = False
        if sql_history:
            from collections import Counter
            counts = Counter(sql.strip() for sql in sql_history if sql.strip())
            if counts and max(counts.values()) >= 2:
                has_duplicate_sql = True

        # 1. 动态权限与工具准备 (Matt Pocock 窄接口剪枝：严防 18 个冗余工具对模型的注意力分散与 Prompt 膨胀)
        user_id = (state.get("metadata") or {}).get("user_id", "default_admin")
        all_tools = skill_registry.get_all_skills()
        filtered_tools = permission_manager.filter_skills(user_id, all_tools)
        CORE_CODER_TOOLS = {"execute_audit_sql", "calculator", "get_table_schema", "audit_medical_rule",
                            "query_law_database", "query_knowledge_base"}
        tools = [t for t in filtered_tools if getattr(t, "name", "") in CORE_CODER_TOOLS]

        # 1.5 快速路由物理直通分流 (Bypass Coder LLM) [Matt Pocock Deep Module: fast_route_executor]
        fast_route_res = await execute_fast_route_bypass(
            state=state,
            tools=tools,
            tracer=tracer,
            retry=retry,
            is_probe_fn=self._is_probe_query
        )
        if fast_route_res.handled and not fast_route_res.fallback_to_llm:
            return fast_route_res.state_update

        # 2. 上下文准备与 Prompt 渲染 [Matt Pocock Deep Module: coder_prompt_assembler]
        metadata = state.get("metadata") or {}
        prompt_payload = assemble_coder_prompt(state, metadata=metadata)
        prompt = prompt_payload.prompt_messages

        # 3. 执行 LLM 思考与强制重试调度 [Matt Pocock Deep Module: coder_inference_coordinator]
        with tracer.span("CODER_REASONING", node="CODER") as span:
            inference_res = await coordinate_coder_inference(
                prompt=prompt,
                state=state,
                config=config,
                tools=tools,
                span=span,
                tracer=tracer,
                is_probe_fn=self._is_probe_query
            )
            if not inference_res.has_tool_calls:
                return inference_res.direct_return_state
            response = inference_res.response
            
            # [Gate 2] SQL物理执行前的语义拦截校验 [Matt Pocock Deep Module]
            pre_check = check_pre_execution_gate(response.tool_calls, state)
            if not pre_check.passed:
                logger.warning(f"🚨 [Gate 2 SQL Semantics Intercept] {pre_check.error}")
                span.fail(pre_check.error)

                history_sql = state.get("sql_history", [])
                preserved_raw_data = state.get("raw_data", "")
                has_valid_execution = state.get("sql_validated", False) and bool(preserved_raw_data)

                # 若已有前序成功取证的有效数据，且本次拦截的是辅助采样，保全数据与验证状态
                if has_valid_execution:
                    logger.info("✨ [Gate 2 State Safeguard] 检测到已存在验证通过的有效审计数据，保全已有取证成果")
                    return {
                        "error_log": None,
                        "sql_validated": True,
                        "sql_query": history_sql[-1] if history_sql else pre_check.sql_arg,
                        "sql_history": history_sql,
                        "raw_data": preserved_raw_data,
                        "messages": [response],
                        "retry_count": retry,
                        "execution_trace": tracer.to_legacy_list(),
                    }

                return {
                    "error_log": pre_check.error,
                    "sql_query": pre_check.sql_arg,
                    "sql_history": history_sql,
                    "raw_data": preserved_raw_data,
                    "messages": [response],
                    "retry_count": retry + 1,
                    "execution_trace": tracer.to_legacy_list(),
                }
            
            span.set_result(f"生成了 {len(response.tool_calls)} 个工具调用指令")

        # 4. 物理工具执行 (SQL 执行)
        with tracer.span("SQL_EXECUTION", node="CODER") as span:
            logger.info(f"🔍 [Tool Execution Debug] Available tools: {[t.name for t in tools]}")
            logger.info(f"🔍 [Tool Execution Debug] Requested tool calls: {response.tool_calls}")
            results = await self._invoke_tools_parallel(response.tool_calls, tools, state)
            logger.info(f"🔍 [Tool Execution Debug] Results: {results}")
            span.set_result(f"物理执行完成，获取 {len(results)} 组结果集")
        
        # 5. 结果聚合与处理 (迁移自原 sqlexec_node)
        processed = self._process_tool_results(results, state)
        
        # 6. 质量门控 (Linter & Booster & Reflexion)
        with tracer.span("QUALITY_GATE", node="CODER") as span:
            if processed["sql_query"]:
                post_check = check_post_execution_gate(
                    sql=processed["sql_query"],
                    methodology=processed["methodology"],
                    raw_data=processed["raw_data"],
                    intent=prompt_payload.audit_intent,
                )
                if not post_check.passed:
                    refl_feedback = post_check.error_feedback or "执行结果异常，触发自愈"
                    logger.warning(f"🚨 [Quality Gate / Reflection Intercept] {refl_feedback}")
                    span.fail(refl_feedback)
                    return {
                        "error_log": refl_feedback,
                        "sql_query": processed["sql_query"],
                        "messages": [response] + processed["tool_msgs"],
                        "retry_count": retry + 1,
                        "execution_trace": tracer.to_legacy_list(),
                    }
                span.set_result("逻辑与数值对齐校验通过")
            else:
                logger.info("未执行 SQL 查询，跳过质量门控")
                span.set_result("跳过质量门控")

        # [V180.0 Pocock 单调保全] 若前序已成功物理取证，后序辅助探针的偶发错误不能撤销已获得的取证资格
        prev_validated = state.get("sql_validated", False) and bool(state.get("raw_data"))
        final_validated = (not processed["has_error"]) or prev_validated
        final_error_log = None if prev_validated else (processed["error_msg"] if processed["has_error"] else None)

        return {
            "raw_data": processed["raw_data"],
            "evidence_row_count": processed["evidence_row_count"],
            "sql_query": processed["sql_query"],
            "sql_history": processed["sql_history"], # [V178.9] 证据链持久化
            "methodology": processed["methodology"],
            "messages": [response] + processed["tool_msgs"],
            "retry_count": retry + 1 if (processed["has_error"] or has_duplicate_sql) else retry,
            "sql_validated": final_validated,
            "error_log": final_error_log,
            "execution_trace": tracer.to_legacy_list(),
            "temp_table": state.get("temp_table")
        }

    async def _invoke_tools_parallel(self, tool_calls, tools, state):
        """委托给 audit_tool_executor 深模块进行安全工具调度与探针拦截 [Matt Pocock Deep Module]"""
        from app.agents.audit_tool_executor import invoke_tools_safely
        return await invoke_tools_safely(tool_calls, tools, state, is_probe_fn=self._is_probe_query)

    def _process_tool_results(self, results, state):
        """委托给 ToolEvidenceExtractor 深模块进行证据链标准化处理。"""
        from app.core.tool_engine.tool_evidence_extractor import tool_evidence_extractor
        return tool_evidence_extractor.process(results, state).to_dict()

    def _run_quality_gates(self, sql, methodology, raw_data, trace=None):
        """[Matt Pocock Deep Module] 委托给专职的质量门控深模块"""
        return run_quality_linter(sql=sql, methodology=methodology, raw_data=raw_data)


coder_agent = AuditCoderAgent()
CoderAgent = AuditCoderAgent
