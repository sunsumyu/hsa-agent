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
from app.memory.semantic_memory import cognitive_memory_manager
from app.skills.schema_injector import schema_injector
from app.infra.neo4j_manager import neo4j_manager
from app.core.prompts import CODER_PROMPT
from app.skills.sql_validator import sql_validator
from app.core.booster import booster
from app.core.structured_tracer import StructuredTracer

from app.skills.probe_guard import is_probe_query

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

        # 1. 动态权限与工具准备
        user_id = (state.get("metadata") or {}).get("user_id", "default_admin")
        all_tools = skill_registry.get_all_skills()
        tools = permission_manager.filter_skills(user_id, all_tools)

        # 1.5 快速路由物理直通分流 (Bypass Coder LLM)
        metadata = state.get("metadata") or {}
        fast_route_id = metadata.get("fast_route_id")
        if fast_route_id:
            logger.success(f"⚡ [Coder Bypass] 智能体命中直通分支，跳过 Coder LLM 生成，直接物理调用工具: {fast_route_id}")
            from langchain_core.messages import AIMessage
            
            tool_calls = [{
                "name": "audit_medical_rule",
                "args": {
                    "rule_id": fast_route_id,
                    "extra_filters": metadata.get("extra_filters")
                },
                "id": f"call_fast_route_{fast_route_id}"
            }]
            
            response = AIMessage(
                content=f"已通过快速路由匹配到静态审计规则: {fast_route_id}，正在执行物理直通计算。",
                tool_calls=tool_calls
            )
            
            with tracer.span("SQL_EXECUTION", node="CODER") as span:
                results = await self._invoke_tools_parallel(tool_calls, tools, state)
                span.set_result(f"物理执行完成，获取 {len(results)} 组结果集")

            processed = self._process_tool_results(results, state)

            # [V+1] 零行兜底 (Fast Route Fallback)：
            # 如果快速路由执行后 raw_data 为空（0 条命中），说明预定义 SQL 与当前数据集不匹配。
            # 此时清除 fast_route_id 标记，让执行流继续往下走 LLM 推理路径，
            # 由 LLM 动态生成适配当前数据集的 SQL，而不是直接输出空报告。
            raw = processed.get("raw_data", "")
            is_empty_result = not raw or raw.strip() in ("", "[]", "None")
            if is_empty_result and not processed["has_error"]:
                logger.warning(
                    f"⚡ [Fast Route Fallback] 规则 {fast_route_id} 物理执行返回 0 行，"
                    f"数据集与模板不匹配，自动降级到 LLM 推理路径以动态适配。"
                )
                # 清除 fast_route_id，继续执行后续 LLM 推理逻辑（不 return）
                metadata.pop("fast_route_id", None)
                state["metadata"] = metadata
                # 将已执行的 SQL 注入 sql_history，让 LLM 知道已尝试过什么
                state.setdefault("sql_history", [])
                if processed["sql_query"]:
                    state["sql_history"].append(processed["sql_query"])
                # fallthrough: 继续走下方的 LLM 推理逻辑
            else:
                return {
                    "raw_data": processed["raw_data"],
                    "sql_query": processed["sql_query"],
                    "sql_history": processed["sql_history"],
                    "methodology": processed["methodology"],
                    "messages": [response] + processed["tool_msgs"],
                    "retry_count": retry,
                    "sql_validated": not processed["has_error"],
                    "error_log": processed["error_msg"] if processed["has_error"] else None,
                    "execution_trace": tracer.to_legacy_list(),
                    "temp_table": state.get("temp_table")
                }

        # 2. 上下文准备
        tasks_list = state.get("tasks", [])

        # [V2.0 NEW] 检查 metadata 中是否有场景强制提示（由 ContextBuilder 注入）
        scene_enforcement = metadata.get("scene_enforcement")

        # 已启用统一 GSSC 上下文引擎，真实 Schema 信息、审计经验及便签线索将由 ContextBuilder 在 LLMProvider 自动挂载至消息链尾部！
        # 传入优雅的定位语，指导模型注意尾部事实载荷
        schema_hint = "【已启用 GSSC 统一上下文引擎：本角色所需的真实 ClickHouse DDL 物理表结构与主表规范，已安全挂载于当前消息流最尾部。请滚动至最尾部，在 <database_schema_context> 标签中查阅，以确保取得最新最准的 DDL 元数据进行 SQL 编写】"
        experiences_combined = "【已启用 GSSC 统一上下文引擎：相关的向量专家经验与外部结构化审计便签线索，已安全挂载于当前消息流最尾部。请滚动至最尾部，在 <experiential_context> 与 <structured_audit_notes> 标签中查阅，以获取历史成功路径与已固化的审计证据链】"
        
        user_q = ""
        for m in state.get("messages", []):
            if isinstance(m, tuple) and len(m) >= 2:
                role, content = m[0], m[1]
                if role in ("user", "human"):
                    user_q += " " + str(content)
            elif isinstance(m, dict):
                role = m.get("role") or m.get("type")
                content = m.get("content") or m.get("text")
                if role in ("user", "human") and content:
                    user_q += " " + str(content)
            elif hasattr(m, "type") and getattr(m, "type") == "human":
                user_q += " " + str(getattr(m, "content", ""))
            elif hasattr(m, "role") and getattr(m, "role") == "user":
                user_q += " " + str(getattr(m, "content", ""))
        user_q = user_q.strip()[:200]

        # ──【企业级 v2.0】场景化 SQL 刚性防漂移指引注入 ──
        q_lower = user_q.lower()
        scenario_guidelines = ""

        # [V2.0 NEW] 优先使用 SceneTableSelector 的强制提示（仅用于表选择，不强制 SQL 模板）
        if scene_enforcement:
            scenario_guidelines = scene_enforcement

        zero_findings_rule = (
            "\n\n【⚠️ 零发现与终止准则 (Zero-Findings & Termination Rule)】\n"
            "1. **禁止分步查证探查**：严禁在编写核心审计 SQL 之前，通过单独执行简单的 `SELECT DISTINCT hilist_name` 或 `count(*)` 探查来预先检查项目/药品/科室是否存在！你必须直接根据审计指引，一次性编写并执行完整的、包含多表 JOIN 关联和复杂业务对碰（如按分钟重叠计算、多重过滤、高值耗材缺失 `countIf` 聚合等）的核心审计 SQL。即使执行后返回空值 `data: []` 也是完全正确和被期望的。\n"
            "2. 当核心 SQL 执行完毕且返回空数据后，你**绝对禁止**进行任何微调重试，此时你**必须且只能执行 1 个简单的边界探针 SQL** 来获取扫描边界数据（例如查询主表总行数和时间范围：`SELECT count(*) as total_cnt, min(setl_time) as min_t, max(setl_time) as max_t FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'`）。\n"
            "3. 边界探针 SQL 执行完后，必须**立即停止调用工具**，并在回复中写明未发现异常的结论，以便系统产出专业的零发现报告。"
        )
        if scenario_guidelines:
            experiences_combined = f"{experiences_combined}{scenario_guidelines}{zero_findings_rule}"
        else:
            experiences_combined = f"{experiences_combined}{zero_findings_rule}"

        prompt = CODER_PROMPT.format_messages(
            original_question=user_q,
            messages=state["messages"], 
            ontology=neo4j_manager.get_ontology(),
            schema_info=schema_hint,
            methodology=state.get("methodology", ""),
            tasks="\n".join(tasks_list), 
            experiences=experiences_combined
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
            
            logger.info(f"🔮 [Coder LLM Response] Content: {str(response.content)[:500]} | Tool Calls: {getattr(response, 'tool_calls', None)}")
            
            if not getattr(response, "tool_calls", None):
                 span.set_result("未触发工具调用，直接回复")
                 # [V178.10] 使用 state 中已累加的全量 sql_history，确保不丢失任何轮次的 SQL
                 history_sql = state.get("sql_history", [])
                 preserved_raw_data = state.get("raw_data", "")
                 logger.info(f"🔮 [DEBUG_SQL_DIRECT] history_sql from state: {history_sql}")
                 logger.info(f"🔮 [DEBUG_SQL_DIRECT] preserved_raw_data: {preserved_raw_data[:200]}...")
                 core_sql = ""
                 if history_sql:
                     audit_queries = []
                     for s in history_sql:
                         is_probe = self._is_probe_query(s)
                         logger.info(f"🔮 [DEBUG_SQL_DIRECT] checking query: is_probe={is_probe} for {s[:100]}...")
                         if not is_probe:
                             audit_queries.append(s)
                     core_sql = audit_queries[-1] if audit_queries else history_sql[-1]
                 logger.info(f"🔮 [DEBUG_SQL_DIRECT] selected core_sql: {core_sql[:100]}...")
                 return {
                     "messages": [response],
                     "error_log": None,
                     "execution_trace": tracer.to_legacy_list(),
                     "sql_query": core_sql,
                     "sql_history": history_sql,  # [V178.10] 返回全量 sql_history，确保不丢失
                     "raw_data": preserved_raw_data  # [V178.10] 显式返回 raw_data，确保前序轮次的审计证据不丢失
                 }
            
            # [V2.0 NEW] SQL物理执行前的语义拦截校验 [Gate 2]
            for tc in response.tool_calls:
                if tc.get("name") == "execute_audit_sql":
                    sql_arg = tc.get("args", {}).get("sql", "")
                    if sql_arg:
                        from app.core.context.gates import QualityGate
                        validation_res = QualityGate.validate_sql_semantics(state, sql_arg)
                        if not validation_res.get("passed", True):
                            gate_error = validation_res.get("error") or "SQL 语义审查校验失败"
                            logger.warning(f"🚨 [Gate 2 SQL Semantics Intercept] {gate_error}")
                            span.fail(gate_error)
                            return {
                                "error_log": gate_error,
                                "sql_query": sql_arg,
                                "messages": [response],
                                "retry_count": retry + 1,
                                "execution_trace": tracer.to_legacy_list()
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
        
        # 6. 质量门控 (Linter & Booster)
        with tracer.span("QUALITY_GATE", node="CODER") as span:
            if processed["sql_query"]:
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
            else:
                logger.info("未执行 SQL 查询，跳过质量门控")
                span.set_result("跳过质量门控")

        return {
            "raw_data": processed["raw_data"],
            "sql_query": processed["sql_query"],
            "sql_history": processed["sql_history"], # [V178.9] 证据链持久化
            "methodology": processed["methodology"],
            "messages": [response] + processed["tool_msgs"],
            "retry_count": retry + 1 if (processed["has_error"] or has_duplicate_sql) else retry,
            "sql_validated": not processed["has_error"],
            "error_log": processed["error_msg"] if processed["has_error"] else None,
            "execution_trace": tracer.to_legacy_list(),
            "temp_table": state.get("temp_table")
        }

    async def _invoke_tools_parallel(self, tool_calls, tools, state):
        # 计算是否已经成功物理执行过核心对碰 SQL
        has_run_core = False
        for prev_sql in state.get("sql_history", []):
            if not self._is_probe_query(prev_sql):
                has_run_core = True
                break

        async def _single_call(tc):
            t_instance = next((t for t in tools if t.name == tc["name"]), None)
            if not t_instance: return tc, {"status": "ERROR", "error_message": f"Unknown tool: {tc['name']}"}
            try:
                args = tc["args"].copy() if isinstance(tc["args"], dict) else {}
                import inspect
                target_func = t_instance.func or getattr(t_instance, "coroutine", None)
                if tc["name"] == "execute_audit_sql" or (target_func and "state" in inspect.signature(target_func).parameters):
                    args["state"] = state
                
                # 刚性物理拦截：如果尚未执行过核心 SQL，禁止执行任何探针探路 SQL
                if tc["name"] == "execute_audit_sql" and not has_run_core:
                    sql_arg = args.get("sql", "")
                    if self._is_probe_query(sql_arg):
                        logger.warning(f"🚨 [PROBE_INTERCEPT] 物理算力引擎拦截了前置探针 SQL: {sql_arg}")
                        return tc, {
                            "status": "ERROR",
                            "error_message": "【算力安全红线拦截】物理算力引擎已禁止前置数据探查！你绝对不能预先执行 DISTINCT med_type 或其他探路 SQL。你必须且只能在第一步中，直接根据 methodology 编写并物理执行最终的核心业务审计 SQL（必须包含 lagInFrame / row_number / OVER / 复杂对碰关联等），哪怕该表物理数据为空，这也是留存物理审计证据的唯一合规方式！",
                            "sql_logic": sql_arg
                        }

                res = await t_instance.ainvoke(args)
                return tc, res
            except Exception as e:
                return tc, {"status": "ERROR", "error_message": str(e)}

        raw_results = []
        for tc in tool_calls:
            res = await _single_call(tc)
            raw_results.append(res)
        return raw_results

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
            
            # [NEW] 智能支持 JSON 字符串响应的解析
            parsed_res = res
            if isinstance(res, str) and res.strip().startswith("{"):
                try:
                    parsed_res = json.loads(res)
                except Exception:
                    try:
                        import ast
                        parsed_res = ast.literal_eval(res)
                    except Exception:
                        pass
            
            if isinstance(parsed_res, dict):
                if "sql_logic" in parsed_res: sql_logics.append(parsed_res["sql_logic"])
                if "methodology" in parsed_res: methodologies.append(parsed_res["methodology"])
                if "trace_hint" in parsed_res: tool_traces.append(f"[{trace_id}] {parsed_res['trace_hint']}")
                if parsed_res.get("status") == "ERROR":
                    has_error = True
                    error_msg = parsed_res.get("error_message") or "Tool execution failed"
                
                # 证据链提取：排除探针查询的数据，避免其污染真实的审计证据链数据
                sql_logic = parsed_res.get("sql_logic", "")
                is_probe = sql_logic and self._is_probe_query(sql_logic)
                
                if not is_probe:
                    if "data" in parsed_res and parsed_res["data"]:
                        raw_data_list.append(str(parsed_res["data"]))
                    elif "records_sample" in parsed_res: 
                        raw_data_list.append(str(parsed_res["records_sample"]))
                    elif "raw_evidence" in parsed_res: 
                        raw_data_list.append(str(parsed_res["raw_evidence"]))
        
        # 启发式筛选核心审计 SQL，避免被最后一步的边界探针 SQL 覆盖
        core_sql = ""
        # [V178.10] 手动累加 sql_history，不依赖 LangGraph reducer（node 内部多次调用不会触发 reducer）
        accumulated_sql_history = state.get("sql_history", []) + sql_logics
        logger.info(f"🔮 [DEBUG_SQL] state.sql_history: {state.get('sql_history')}")
        logger.info(f"🔮 [DEBUG_SQL] current sql_logics: {sql_logics}")
        logger.info(f"🔮 [DEBUG_SQL] accumulated_sql_history: {accumulated_sql_history}")
        if accumulated_sql_history:
            audit_queries = []
            for sql in accumulated_sql_history:
                is_probe = self._is_probe_query(sql)
                logger.info(f"🔮 [DEBUG_SQL] checking query: is_probe={is_probe} for {sql[:100]}...")
                if not is_probe:
                    audit_queries.append(sql)
            if audit_queries:
                core_sql = audit_queries[-1]
            else:
                core_sql = accumulated_sql_history[-1]
        logger.info(f"🔮 [DEBUG_SQL] selected core_sql: {core_sql[:100]}...")

        # 判断本轮是否执行了新的核心审计 SQL
        has_new_core_query = False
        for sql in sql_logics:
            if not self._is_probe_query(sql):
                has_new_core_query = True
                break

        new_raw_data = "\n---\n".join(raw_data_list)
        if not has_new_core_query and not new_raw_data:
            new_raw_data = state.get("raw_data", "")

        # [V2.1] 避免在工具未返回 methodology 时将 state 中的 methodology 覆盖为空字符串
        final_methodology = "\n\n".join(methodologies) if methodologies else state.get("methodology", "")

        return {
            "tool_msgs": tool_msgs,
            "raw_data": new_raw_data,
            "sql_query": core_sql,
            "sql_history": accumulated_sql_history, # [V178.10] 返回全量累加 sql_history，不依赖 LangGraph reducer
            "methodology": final_methodology,
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
