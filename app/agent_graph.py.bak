import operator
import re
from typing import Annotated, Sequence, TypedDict, Dict, List, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
import app.logging_config # [V41.6] 物理链路可跳转配置
import asyncio

from app.usage_tracker import usage_tracker
from app.model_manager import model_manager
from app.prompts import PLANNER_PROMPT, CODER_PROMPT, ANALYST_PROMPT, REPORTER_PROMPT, AUDITOR_PROMPT
from app.tools import execute_audit_sql, get_table_schema, list_tables, search_expert_knowledge
from app.experience import experience_manager
from app.semantic_layer import SemanticRetriever
from app.semantic_memory import cognitive_memory_manager
from app.rich_reporter import RichReportGenerator
from app.security import SQLGuardian, SecurityViolationError
from app.llm_judge import audit_judge
from app.conflict_detector import detect_conflicts
# [V58.9.2] 引入三个与业务解耦的可复用模块
from app.message_sanitizer import sanitize_for_thinking_mode, trim_and_sanitize
from app.report_renderer import report_renderer as _report_renderer
from app.fast_router import fast_router as _fast_router, RouteType
# [V59.2] M4 精准 Schema 注入 + M5 结构化执行追踪
from app.schema_injector import schema_injector as _schema_injector
from app.structured_tracer import StructuredTracer
import json
import os
from app.observability import build_obs_config, get_langfuse_prompt
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

# 初始化语义检索器
semantic_retriever = SemanticRetriever()

# ============================================================
# 1. Structured Output Schemas
# ============================================================

class AuditFinding(BaseModel):
    violation_type: str = Field(description="认定的违规类型")
    evidence: str = Field(description="证据描述，必须包含核心数值")
    amount: float = Field(description="涉及金额")
    count: int = Field(description="涉及违规次数")
    policy_basis: str = Field(description="政策依据")

class AuditReport(BaseModel):
    summary: str = Field(description="任务总结")
    findings: List[AuditFinding] = Field(description="发现列表")
    total_amount: float = Field(description="总计金额")
    finding_count: int = Field(default=0, description="发现的记录总数")
    risk_level: str = Field(description="高/中/低")
    risk_scores: Dict[str, int] = Field(default_factory=lambda: {"取证清晰度": 80, "经济影响": 50, "再犯风险": 30, "政策复杂性": 40, "发现隐蔽性": 60})

class AuditFeedback(BaseModel):
    decision: str = Field(description="判定结果: PASS 或 REJECT")
    reason: str = Field(description="拒绝或通过的详细理由")
    corrective_action: Optional[str] = Field(default=None, description="如果拒绝，给出的具体修正指令")

# --- 常量配置 ---
MAX_RETRIES = 3

# ============================================================
# 2. State 定义
# ============================================================

def _sanitize_for_thinking_mode(messages: List) -> List:
    """[V58.9.2] 委托给与业务解耦的独立模块 app.message_sanitizer"""
    return sanitize_for_thinking_mode(messages)

def _trim_messages(left: List, right: List) -> List:
    """[V58.9.2] 升级：委托给 trim_and_sanitize，内置消息合并 + Thinking Mode 净化"""
    return trim_and_sanitize(left, right, max_total=15, keep_head=3, keep_tail=7)

def _merge_dict(left: Dict, right: Dict) -> Dict:
    new = (left or {}).copy()
    new.update(right or {})
    return new

class AuditState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], _trim_messages]
    tasks: List[str]
    sql_query: str
    raw_data: str
    audit_findings: List[AuditFinding]
    structured_report: Optional[AuditReport]
    metadata: Annotated[Dict[str, Any], _merge_dict]
    session_id: str
    error_log: str
    audit_feedback: Optional[AuditFeedback]
    retry_count: int
    human_input: Optional[str]
    is_awaiting_human: bool
    sql_validated: bool
    loop_count: int
    next_step: str
    schema_hint: Optional[str]   # NEED_SCHEMA 补充检索后的字段字典
    execution_trace: List[str]   # [V57.0] 审计执行轨迹：记录每步 SQL/工具 的物理行为日志



# ============================================================
# 2.5 [V57.0] 审计轨迹安全工具
# ============================================================

_SENSITIVE_PATTERNS = [
    # 内网 IP
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[IP已脏敏]'),
    # ClickHouse 连接字符串
    (re.compile(r'clickhouse://[^\s]+', re.IGNORECASE), '[DSN已脏敏]'),
    # 密码模式
    (re.compile(r'password=[^\s&]+', re.IGNORECASE), 'password=[REDACTED]'),
    # 原始表名（防止泳露内部数据模型）
    (re.compile(r'fqz_[a-z_]+', re.IGNORECASE), '[TABLE]'),
]

MAX_TRACE_ENTRIES = 5  # 最多保留最近 5 条记录，防止 Token 爆炸

def _sanitize_trace(text: str) -> str:
    """[V57.0] 对轨迹文本进行脚敏化处理，防止内网信息泳露。"""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

def _append_trace(state: dict, entry: str) -> List[str]:
    """[V57.0] 安全地将一条记录写入轨迹，并限制总条数不超过 MAX_TRACE_ENTRIES。"""
    trace = list(state.get("execution_trace") or [])
    trace.append(_sanitize_trace(entry))
    return trace[-MAX_TRACE_ENTRIES:]  # 只保留最新的 N 条



async def planner_node(state: AuditState, config: RunnableConfig):
    # ── 安全提取用户输入 ─────────────────────────────────────────
    user_input = ""
    if state.get("messages") and len(state["messages"]) > 0:
        first_msg = state["messages"][0]
        if isinstance(first_msg, tuple):
            user_input = first_msg[1]
        else:
            user_input = getattr(first_msg, "content", str(first_msg))

    # ── [V48.0] 语义 SQL 缓存拦截（最高优先级）─────────────────────
    from app.semantic_memory import sql_cache_manager
    cached_sql = sql_cache_manager.search(user_input)
    if cached_sql:
        logger.success("⚡ [CACHE HIT] 命中问题语义缓存，直接短路 Planner 与 Coder！")
        return {
            "tasks": ["(Cached) 执行已验证的精准 SQL"],
            "sql_query": cached_sql,
            "cache_hit": True,
            "messages": []
        }

    # ── [V59.1] Fast Route 拦截：已知规则类任务跳过 LLM，直接走算子 ───
    route = _fast_router.classify(user_input)
    if route.route_type != RouteType.UNKNOWN:
        logger.success(
            f"🚀 [FAST_ROUTE] 命中已知规则 [{route.target_id}] "
            f"置信度={route.confidence:.0%} | {route.reason}"
        )
        trace = _append_trace(state, f"[FastRoute] 跳过LLM直接路由 → {route.target_id} (置信度{route.confidence:.0%})")

        # 根据路由类型选择对应工具名（AUDITOR 节点会调用这些工具）
        if route.route_type == RouteType.KNOWN_RULE:
            task_desc = f"使用 audit_medical_rule 工具，规则ID: {route.target_id}"
        else:
            task_desc = f"使用 run_anomaly_detection 工具，算法ID: {route.target_id}"

        return {
            "tasks": [task_desc],
            "metadata": {
                "fast_route_id": route.target_id,
                "fast_route_type": route.route_type.value,
                "user_question": user_input,  # [ISS-009 Fix] 保存原始问题供 Reporter 使用
            },
            "retry_count": 0,
            "execution_trace": trace,
            # [ISS-009 Fix] 保留原始 messages，不新增以避免 tuple/HumanMessage 混合
            "messages": list(state.get("messages", []))
        }

    # ── [V47.3] LLM 推理路径（仅未知/复杂类任务）───────────────────
    complexity = model_manager.classify_complexity_locally(user_input)
    logger.info(f"💡 [ROUTER] 本地语义路由决策结果: {complexity}")

    role = "planner_heavy" if complexity == "HIGH" else "planner_light"
    llm, actual_model = model_manager.get_llm_by_role(role, retry_count=state.get("retry_count", 0), config=config)

    mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), user_input)

    prompt_template = get_langfuse_prompt("planner-audit-v1", fallback=PLANNER_PROMPT)
    prompt = prompt_template.format_messages(messages=state["messages"], experiences=mem_context)
    obs_config = build_obs_config(config, role, state)
    logger.debug(f">>> [执行期诊断] 节点角色: {role} | LLM对象: {llm} | 实际模型ID: {actual_model}")
    response = await llm.ainvoke(prompt, config=obs_config)
    _record_usage_with_budget(role, response, actual_model, prompt=prompt)
    content = str(response.content)

    cognitive_memory_manager.add_message(state.get("session_id", "default"), response)

    tasks = [re.sub(r'^[\-\*123\.]\s*', '', line).strip() for line in content.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3."))]
    return {"tasks": tasks[:3], "messages": [response], "retry_count": 0, "complexity": complexity}

async def sqlexec_node(state: AuditState, config: RunnableConfig):
    retry = state.get("retry_count", 0)
    if retry >= MAX_RETRIES:
        logger.error(f"🛑 [SQLEXEC] 达到重试上限 ({MAX_RETRIES}次)，强制熔断并汇报失败。")
        return {
            "raw_data": "【审计异常】由于系统在 3 次重试内均未能生成有效取证逻辑或遭遇持续错误，本次任务已强制终止。建议人工核查业务口径或补充物理字典。",
            "sql_validated": True,
            "error_log": "REACHED_MAX_RETRIES"
        }
    # ── [V59.1] Fast Route 直接执行：跳过 LLM Coder ─────────────────
    fast_route_id = (state.get("metadata") or {}).get("fast_route_id")
    fast_route_type = (state.get("metadata") or {}).get("fast_route_type")
    if fast_route_id:
        logger.success(f"🚀 [FAST_EXEC] Fast Route 直接执行算子 [{fast_route_id}]，LLM Coder 休眠")
        from app.tools import audit_medical_rule, run_anomaly_detection
        try:
            # [V60.0 P0 修复] 异步工具必须使用 ainvoke，同步 invoke 会在事件循环中阻塞/挂起
            if fast_route_type == RouteType.KNOWN_RULE.value:
                tool_result = await audit_medical_rule.ainvoke({"rule_id": fast_route_id})
            else:
                tool_result = await run_anomaly_detection.ainvoke({"algorithm_id": fast_route_id})

            # tool_result 可能是 dict 或被 LangChain 序列化为字符串
            if isinstance(tool_result, str):
                import json as _j
                try:
                    tool_result = _j.loads(tool_result)
                except Exception:
                    tool_result = {"report": tool_result, "evidence_count": 0, "raw_evidence": []}

            raw_evidence = tool_result.get("raw_evidence", [])
            import json as _j
            import datetime as _dt
            from decimal import Decimal as _Dec

            class _AuditEncoder(_j.JSONEncoder):
                """[ISS-006 Fix] 支持 datetime.date/datetime 和 Decimal 的审计专用序列化器"""
                def default(self, obj):
                    if isinstance(obj, (_dt.datetime, _dt.date)):
                        return obj.isoformat()
                    if isinstance(obj, _Dec):
                        return float(obj)
                    return super().default(obj)

            result_str = (
                _j.dumps(raw_evidence, ensure_ascii=False, cls=_AuditEncoder)
                if isinstance(raw_evidence, list)
                else str(raw_evidence)
            )

            ev_count = tool_result.get("evidence_count", len(raw_evidence) if isinstance(raw_evidence, list) else 0)
            trace = _append_trace(state, f"[FastExec] {fast_route_id} → 命中 {ev_count} 条违规记录")
            logger.success(f"✅ [FAST_EXEC] 算子 {fast_route_id} 执行完毕，命中 {ev_count} 条")
            return {
                "raw_data": result_str,
                "sql_query": f"-- FastRoute: {fast_route_id}",
                "sql_validated": True,
                "error_log": None,
                "execution_trace": trace,
            }
        except Exception as e:
            logger.warning(f"⚠️ [FAST_EXEC] Fast Route 执行异常，降级到 LLM 路径: {e}")
            # 降级：清除 fast_route_id，允许 LLM Coder 接管
            state_metadata = dict(state.get("metadata") or {})
            state_metadata.pop("fast_route_id", None)

    
    logger.info(f">>> [SQLEXEC] 正在物理取证... (尝试 {retry + 1}/3)")
    from app.tools import audit_medical_rule, run_anomaly_detection, search_expert_knowledge, get_table_schema
    llm, actual_model = model_manager.get_llm_by_role("coder", retry_count=retry, config=config)
    
    tools = [audit_medical_rule, run_anomaly_detection, search_expert_knowledge, get_table_schema]
    llm_with_tools = llm.bind_tools(tools)
    tasks_list = state.get("tasks", [])
    # ── [V59.2] M4 精准 Schema 注入（替代全量 FAISS Schema 堆砌）────────
    schema_override = state.get("schema_hint")
    if schema_override:
        semantic_dict = schema_override
        logger.info("[SQLEXEC] 使用 NEED_SCHEMA 补充 Schema 重试")
    else:
        # 精准召回：只注入与当前任务最相关的 6 个字段（约 600 字符 vs 旧版 3000+ 字符）
        user_q = ""
        for m in state.get("messages", []):
            c = getattr(m, "content", "")
            if c:
                user_q = str(c)
                break
        task_hint = " ".join(state.get("tasks", []))
        semantic_dict = _schema_injector.inject(
            user_question=f"{user_q} {task_hint}",
            top_k=6,
            max_chars=700,
        )
        logger.debug(f"[SQLEXEC] 精准 Schema ({len(semantic_dict)} chars)")
    
    # [V47.7] 统一记忆召回：结合传统经验与语义记忆
    mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), "\n".join(tasks_list))
    relevant_experiences = experience_manager.get_relevant_experience(tasks_list)
    combined_exp = f"{mem_context}\n\n{relevant_experiences}"
    
    # [V51.0 深度优化] 吸收 hello-agents Chapter 7/9 的 Observation 模式
    if retry > 0:
        # 1. 提取核心指令
        sys_msgs = [m for m in state["messages"] if isinstance(m, SystemMessage)]
        user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        
        # 2. 构造 Observation 日志（模仿 ReAct 模式）
        # 将失败历史重塑为“外部观察事实”，而不是“对话历史”
        observation_log = f"\n### 📝 物理取证观察日志 (Audit Observation Log):\n"
        observation_log += f"- 上轮状态: REJECTED\n"
        observation_log += f"- 拦截原因: {state.get('error_log', 'Unknown Error')}\n"
        
        if state.get("schema_hint"):
            observation_log += f"- [关键发现] 已锁定物理映射: {state['schema_hint']}\n"
        
        # 3. 构造 State Reflection 指令
        reflection_instruction = HumanMessage(content=(
            f"{observation_log}\n"
            f"### 🎯 当前指令 (Refined Instruction):\n"
            f"根据上述观察结果，修正逻辑并重新生成 SQL。请严格遵守物理字典，禁止幻觉。\n"
            f"待执行任务: " + "\n".join(tasks_list)
        ))
        
        # 只保留最核心的消息对，防止 Context Collapse
        clean_state_messages = (sys_msgs[:1] + user_msgs[:1] + [reflection_instruction])
        logger.info(f"[SQLEXEC] Context Reshaped via hello-agents Observation pattern.")
    else:
        clean_state_messages = state["messages"]

    prompt_template = get_langfuse_prompt("coder-sql-expert-v1", fallback=CODER_PROMPT)
    prompt = prompt_template.format_messages(
        messages=clean_state_messages, schema_info=semantic_dict,
        tasks="\n".join(tasks_list), experiences=combined_exp, semantic_dict=semantic_dict
    )
    
    if tasks_list and not state.get("human_input"):
        prompt.append(HumanMessage(content=f"请根据计划执行取证：\n" + "\n".join(tasks_list)))

    obs_config = build_obs_config(config, "sqlexec", state)
    response = await llm_with_tools.ainvoke(prompt, config=obs_config)
    _record_usage_with_budget("coder", response, actual_model, prompt=prompt)
    
    # 工具调用路径
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
        for t_call, res in results:
            if res is not None:
                tool_msg = ToolMessage(content=str(res), tool_call_id=t_call["id"])
                tool_msgs.append(tool_msg)
                raw_data_list.append(str(res))
                # [V47.0] 将关键取证数据记录为情景记忆
                cognitive_memory_manager.add_message(state.get("session_id", "default"), tool_msg)
                
        combined_raw = "\n---\n".join(raw_data_list)
        # [V37.7] 强制持久化取证数据到文件
        with open("data/raw_audit_evidence_dump.json", "w", encoding="utf-8") as f:
            json.dump({"raw": combined_raw}, f, ensure_ascii=False)

        # [V57.0] 从工具返回值中提取 trace_hint，写入执行轨迹
        tool_traces = []
        for _, res in results:
            if isinstance(res, dict) and "trace_hint" in res:
                tool_traces.append(res["trace_hint"])
        trace = list(state.get("execution_trace") or [])
        for hint in tool_traces:
            trace = _append_trace({"execution_trace": trace}, hint)

        # [Fix-2] 若工具返回空 evidence，直接标记完成，不触发 retry
        any_evidence = any(
            isinstance(r, dict) and r.get("evidence_count", 0) > 0
            for _, r in results if isinstance(r, dict)
        ) or bool(combined_raw.strip())
        return {
            "raw_data": combined_raw,
            "messages": [response] + tool_msgs,
            "retry_count": retry + 1,
            "sql_validated": True,   # 工具路径视为已完成，不再重试
            "error_log": None,
            "execution_trace": trace
        }
    
    response_text = str(response.content).strip()

    # ── 路径 0: NEED_SCHEMA ──────────────────────────────────────
    if response_text.startswith("NEED_SCHEMA"):
        missing = [l.replace("- missing:", "").strip()
                   for l in response_text.split("\n") if "missing:" in l]
        reason  = next((l.replace("- reason:", "").strip()
                        for l in response_text.split("\n") if "reason:" in l), "")
        logger.warning(f"[SQLEXEC] NEED_SCHEMA: 缺失字段 {missing}")
        # 触发 semantic_layer 补充检索
        if missing and retry < MAX_RETRIES - 1:
            new_items = semantic_retriever.get_relevant_columns([" ".join(missing)])
            new_dict  = semantic_retriever.format_for_prompt(new_items)
            if new_dict and "暂未检索到" not in new_dict:
                logger.info("[SQLEXEC] 補充 Schema 检索成功，触发重试")
                return {
                    "error_log": f"NEED_SCHEMA，已補充字典，重试中",
                    "messages": [response],
                    "retry_count": retry + 1,
                    "schema_hint": new_dict,
                }
        # 不能補充 → 诚实兄底（不再 retry）
        missing_str = "、".join(missing) if missing else "关键业务字段"
        return {
            "raw_data": (
                f"【审计说明】本次核查任务涉及 {missing_str}，"
                f"当前数据字典未检索到对应物理字段映射。"
                f"{reason}。建议补充以下字段的物理映射后重新执行：{missing_str}。"
            ),
            "sql_validated": True,
            "error_log": None,
            "messages": [response],
            "retry_count": retry + 1,
        }

    # ── 路径 0b: 文本格式 TOOL_CALL （bind_tools 失效时的兑底解析） ──────
    if not getattr(response, "tool_calls", None) and response_text.startswith("TOOL_CALL:"):
        lines     = response_text.split("\n")
        tool_name = lines[0].replace("TOOL_CALL:", "").strip()
        args_str  = next((l.replace("ARGS:", "").strip()
                          for l in lines if l.strip().startswith("ARGS:")), "{}")
        try:
            args          = json.loads(args_str)
            tool_instance = next((t for t in tools if t.name == tool_name), None)
            if tool_instance:
                res      = await tool_instance.ainvoke(args)
                tool_msg = ToolMessage(content=str(res), tool_call_id="text_fallback_0")
                combined = str(res)
                with open("data/raw_audit_evidence_dump.json", "w", encoding="utf-8") as f:
                    json.dump({"raw": combined}, f, ensure_ascii=False)
                return {
                    "raw_data": combined,
                    "messages": [response, tool_msg],
                    "retry_count": retry + 1,
                    "sql_validated": True,
                    "error_log": None,
                }
        except Exception as e:
            logger.warning(f"[SQLEXEC] 文本 TOOL_CALL 解析失败: {e}")

    # SQL 路径：强化正则解析，支持大小写及不规范换行
    sql_match = re.search(r'```(?:sql|SQL)?\n?(.*?)\n?```', response_text, re.DOTALL | re.IGNORECASE)
    sql = sql_match.group(1).strip() if sql_match else response_text
    
    # 物理过滤：剔除可能夹带的 Markdown 标记
    sql = re.sub(r'^```sql\s*|\s*```$', '', sql, flags=re.IGNORECASE | re.MULTILINE).strip()
    
    # [V41.7] 增强错误归因：在进入语法校验前，明确判断空 SQL 的根本原因
    if not sql:
        finish_reason = ""
        if hasattr(response, "response_metadata"):
            finish_reason = response.response_metadata.get("finish_reason", "未知")
            
        if not response_text:
            error_reason = f"Agent 输出了空内容 (底层结束原因: {finish_reason})。"
            if finish_reason.lower() in ["safety", "content_filter", "recitation"]:
                error_reason += " 🛑 明确判定：触发了模型提供商的安全、敏感词或背诵拦截策略。"
            elif finish_reason.lower() in ["stop", "end_turn"]:
                error_reason += " ⚠️ 模型主动停止了生成，可能是它没有理解指令，或者认为不需要执行 SQL。"
        elif "```" in response_text:
            error_reason = "Agent 输出了代码块标记，但内部没有包含任何实际的 SQL 语句。"
        else:
            error_reason = f"Agent 没有生成有效的 SQL 格式，而是输出了普通对话文本：'{response_text[:150]}...'"
            
        detailed_error = f"SQL 内容不能为空。根本原因: {error_reason}"
        logger.warning(f"[SQLEXEC 诊断] 尝试 {retry+1} 失败: {detailed_error}")
        trace = _append_trace(state, f"[SQL失败] 尝试 {retry+1}/3：{error_reason[:150]}")
        return {"error_log": detailed_error, "messages": [response], "retry_count": retry + 1, "execution_trace": trace}

    try:
        sql = SQLGuardian.validate_sql(sql)
        # [V60.0 P0 修复] execute_audit_sql 是异步 @tool，必须通过 ainvoke 调用
        # 直接调用 execute_audit_sql(sql) 只会返回 Coroutine 对象，查询从未真实发出
        result_raw_obj = await execute_audit_sql.ainvoke({"sql": sql})
        result_raw = str(result_raw_obj) if result_raw_obj is not None else ""
        # [V37.7] 强制持久化
        with open("data/raw_audit_evidence_dump.json", "w", encoding="utf-8") as f:
            json.dump({"sql": sql, "raw": result_raw}, f, ensure_ascii=False)
        # [V57.0] 将执行行为写入审计轨迹（已脏敏 + 限长）
        trace = _append_trace(state, f"[SQL执行] {sql.strip()[:200]} → 返回: {result_raw[:80]}")
        logger.success(f"✅ [SQL] 执行成功，结果长度 {len(result_raw)} chars")
        return {
            "raw_data": result_raw, 
            "sql_query": sql, 
            "messages": [response], 
            "retry_count": retry + 1, 
            "sql_validated": True,
            "error_log": None,
            "execution_trace": trace
        }
    except Exception as e:
        logger.warning(f"SQLEXEC 尝试 {retry+1} 失败: {e}")
        trace = _append_trace(state, f"[SQL失败] 尝试 {retry+1}/3：{str(e)[:150]}")
        return {"error_log": str(e), "messages": [response], "retry_count": retry + 1, "execution_trace": trace}

async def auditor_node(state: AuditState, config: RunnableConfig):
    """
    [V60.0 架构升级] 企业级 AUDITOR 节点：
    - 对 Fast Route 路径（物理算子已执行）直接 PASS，无需 SQL 语法审计
    - 对 LLM Coder 生成的 SQL 执行逻辑完整性 + ClickHouse 语法审查
    - 内嵌 CRITIC 过滤逻辑（不产生循环）
    """
    logger.info(">>> [AUDITOR] 正在进行技术审计与逻辑对撞...")

    # ── [ISS-005 Fix] Fast Route 豁免：物理算子已执行，无 SQL 可审计 ────────
    fast_route_id = (state.get("metadata") or {}).get("fast_route_id")
    if fast_route_id:
        import json as _fj
        raw_str = state.get("raw_data", "[]")
        try:
            ev_count = len(_fj.loads(raw_str)) if isinstance(raw_str, str) and raw_str.strip().startswith("[") else 0
        except Exception:
            ev_count = 0
        feedback = AuditFeedback(
            decision="PASS",
            reason=(
                f"[FastRoute 豁免] 物理算子 {fast_route_id} 已通过 ainvoke 直接执行，"
                f"命中 {ev_count} 条记录。Fast Route 路径无 LLM 生成 SQL，无需 SQL 语法审计，直接通过。"
            )
        )
        trace = _append_trace(state, f"[AUDITOR] FastRoute PASS → {fast_route_id}，命中 {ev_count} 条")
        logger.success(f"✅ [AUDITOR] Fast Route 豁免通过: {fast_route_id}")
        return {"audit_feedback": feedback, "is_awaiting_human": False, "execution_trace": trace}

    llm, _ = model_manager.get_llm_by_role("planner", config=config)
    prompt_template = get_langfuse_prompt("auditor-chief-v1", fallback=AUDITOR_PROMPT)
    safe_messages = _sanitize_for_thinking_mode(list(state["messages"]))
    prompt = prompt_template.format_messages(
        messages=safe_messages,
        tasks="\n".join(state["tasks"]),
        sql=state.get("sql_query", "N/A"),
        raw_data_sample=str(state.get("raw_data", ""))[:1000]
    )

    # ── 确定性冲突检测（不需要 LLM）─────────────────────────────
    findings_texts = [f.evidence for f in state.get("audit_findings", [])]
    conflicts = detect_conflicts(findings_texts)
    if conflicts:
        logger.warning(f">>> [CONFLICT] 检测到 {len(conflicts)} 处审计事实矛盾！触发人工审核拦截。")
        return {
            "audit_feedback": AuditFeedback(decision="REJECT", reason=f"检测到物理事实冲突: {conflicts[0]['description']}"),
            "is_awaiting_human": True,
            "retry_count": state.get("retry_count", 0) + 1
        }

    # ── LLM 审计判定─────────────────────────────────────
    try:
        response = await llm.ainvoke(prompt)
        res_text = str(getattr(response, "content", response)).strip()
        json_match = re.search(r'(\{.*\})', res_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            feedback = AuditFeedback(**data)
        else:
            feedback = AuditFeedback(
                decision="PASS" if "PASS" in res_text.upper() else "REJECT",
                reason=res_text[:200]
            )
    except Exception as e:
        logger.error(f"[AUDITOR_ERROR] 解析失败: {e}")
        feedback = AuditFeedback(decision="PASS", reason=f"解析兜底通过: {str(e)}")

    # ── [V59.3] 内嵌 Judge 连锁：AUDITOR PASS 后内联过滤误报（取代独立的 CRITIC 节点）
    if feedback.decision == "PASS":
        report = state.get("structured_report")
        if report and report.findings:
            raw_data_str = str(state.get("raw_data", ""))
            valid_findings = []
            try:
                eval_tasks = [
                    audit_judge.evaluate_finding(f.dict(), raw_data_str)
                    for f in report.findings
                ]
                judge_results = await asyncio.gather(*eval_tasks, return_exceptions=True)
                for finding, result in zip(report.findings, judge_results):
                    if isinstance(result, Exception):
                        valid_findings.append(finding)  # 判断异常则保留
                        continue
                    if result.get("is_valid") and result.get("confidence_score", 0) > 60:
                        valid_findings.append(finding)
                    else:
                        logger.warning(f"🚨 [INLINE_JUDGE_REJECT] 线索被推翻: "
                                       f"{finding.violation_type} | {result.get('refutation_reason', '')}")
                report.findings = valid_findings
                report.finding_count = len(valid_findings)
                logger.info(f"✅ [INLINE_JUDGE] 过滤完成：{len(valid_findings)}/{len(judge_results)} 条线索通过终审")
            except Exception as je:
                logger.warning(f"⚠️ [INLINE_JUDGE] Judge 错误，所有线索保留: {je}")

    trace = _append_trace(state, f"[AUDITOR] 判定结果={feedback.decision} | {feedback.reason[:80]}")
    return {
        "audit_feedback": feedback,
        "is_awaiting_human": False,
        "execution_trace": trace
    }

async def reporter_node(state: AuditState, config: RunnableConfig):
    """[V59.0] 确定性五章节报告渲染器：LLM 只写结论段，其余全部确定性生成。"""
    logger.info(">>> [REPORTER] 正在渲染报告（确定性五章节模式）...")
    from app.booster import booster
    import json as _json

    # ── Step 1: 物理去污 ─────────────────────────────────────────
    raw_data_str = state.get("raw_data", "")
    if isinstance(raw_data_str, str):
        clean_data = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_data_str)
        clean_data = re.sub(r'\\x[0-9a-fA-F]{2}', '', clean_data)
    else:
        clean_data = str(raw_data_str)

    hard_sum, hard_count, _ = booster.calculate_hard_metrics(clean_data)

    # ── Step 2: 解析原始数据为结构化 List[Dict]（供渲染器生成证据表格） ───
    # [ISS-006 Fix] 双轨解析：JSON 优先 + ast.literal_eval 兜底（兼容 datetime 等 Python 原生类型）
    raw_data_list = []
    try:
        cleaned = clean_data.strip()
        if cleaned.startswith("["):
            # 优先标准 JSON 解析（Fix-006a 已修复 datetime 序列化）
            parsed = _json.loads(cleaned)
            if isinstance(parsed, list):
                raw_data_list = parsed[:50]
        if not raw_data_list and cleaned.startswith("["):
            # 兜底：ast.literal_eval 支持 datetime.date() 等 Python repr
            import ast as _ast
            import datetime as _dt
            # 注入 datetime 上下文
            eval_globals = {"datetime": _dt, "date": _dt.date, "Decimal": __import__("decimal").Decimal}
            parsed_py = _ast.literal_eval(cleaned)
            if isinstance(parsed_py, list):
                # 将 datetime.date 对象转为 ISO 字符串以便 JSON 渲染
                def _coerce(row):
                    return {
                        k: (v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else
                            float(v) if hasattr(v, '__float__') and not isinstance(v, (int, float)) else v)
                        for k, v in row.items()
                    } if isinstance(row, dict) else row
                raw_data_list = [_coerce(r) for r in parsed_py[:50]]
    except Exception:
        pass  # 解析失败则以空列表继续，报告仍可正常生成


    # ── Step 3: 提取审计任务上下文（优先从 metadata 读取，Fast Route 路径下 messages=[]）──
    user_question = (
        # [ISS-009 Fix] Fast Route 路径：从 metadata 直接读取原始问题
        (state.get("metadata") or {}).get("user_question")
        or
        # LLM 路径：从 HumanMessage 或 tuple 消息链中遍历提取
        next(
            (
                # 将 tuple 和 HumanMessage 都封装为安全提取
                (msg[1] if isinstance(msg, tuple) else str(getattr(msg, "content", "")))
                for msg in state.get("messages", [])
                if (
                    (isinstance(msg, tuple) and msg[0] in ("user", "human"))
                    or (
                        not isinstance(msg, tuple)
                        and ("human" in getattr(msg, "type", msg.__class__.__name__).lower()
                             or "user" in getattr(msg, "type", msg.__class__.__name__).lower())
                    )
                )
            ),
            ""
        )
    )

    sql_query = state.get("sql_query", "")
    execution_trace = list(state.get("execution_trace") or [])

    # ── Step 4: 调用 LLM 只生成第四章"核查结论"（约 150~300 字）───────
    llm_conclusion = ""
    try:
        llm, _ = model_manager.get_llm_by_role("reporter", config=config)

        # [V59.0] 极简 Conclusion Prompt：只要求生成结论段，严格控制输出长度
        CONCLUSION_PROMPT = (
            "你是一名医保基金稽核专家。根据以下审计信息，用 150~300 字的专业语言"
            "撰写「核查结论」，要求：①明确说明是否发现违规；②列出关键数据指标；"
            "③给出整改建议。只需输出结论段落本身，不需要标题。\n\n"
            f"审计任务：{user_question[:300]}\n\n"
            f"执行轨迹摘要：{'; '.join(execution_trace[-3:]) if execution_trace else '已完成数据核查'}\n\n"
            f"数据概览：共检索 {hard_count} 条记录，涉及金额 ¥{hard_sum:,.2f}"
        )

        from langchain_core.messages import HumanMessage as _HM
        resp = await llm.ainvoke([_HM(content=CONCLUSION_PROMPT)], max_tokens=512)
        llm_conclusion = str(getattr(resp, "content", resp)).strip()
        logger.info(f"✅ [REPORTER] 结论段生成完成，长度: {len(llm_conclusion)} 字")
    except Exception as e:
        logger.warning(f"⚠️ [REPORTER] LLM 结论生成失败，将使用兜底文本: {e}")
        llm_conclusion = (
            f"经数据库核查，本次共检索 {hard_count} 条相关结算记录，"
            f"涉及金额 ¥{hard_sum:,.2f}。"
            + ("如实际发现违规迹象，请结合证据表格进一步复核。" if hard_count > 0 else "未在当前核查口径下检出违规记录。")
        )

    # ── Step 5: 调用确定性渲染器生成完整五章节报告 ────────────────────
    rendered = _report_renderer.render(
        user_question=user_question or "医保专项审计",
        llm_conclusion=llm_conclusion,
        raw_data=raw_data_list,
        sql_query=sql_query,
        table_info="fqz_gz_jzsj_all_ql（全量结算明细）",
        total_amount=hard_sum,
        finding_count=hard_count,
        policy_basis="《医保基金监管条例》",
        execution_trace=execution_trace,
    )

    content = rendered.markdown
    logger.success(f"📋 [REPORTER] 五章节报告渲染完成 | 风险: {rendered.risk_level} | 金额: ¥{rendered.total_amount:,.2f}")

    # ── Step 6: 构建结构化 AuditReport 对象（供下游节点使用） ──────────
    report = AuditReport(
        summary=rendered.summary,
        findings=[],
        total_amount=rendered.total_amount,
        finding_count=rendered.finding_count,
        risk_level=rendered.risk_level,
    )

    # ── Step 7: 记录到长程记忆 + 生成 HTML 仪表盘 ───────────────────
    final_msg = AIMessage(content=content)
    cognitive_memory_manager.add_message(state.get("session_id", "default"), final_msg, importance=0.9)

    try:
        report_data = {
            "report_id": f"HSA-{state.get('session_id', 'AUTO')}",
            "total_amount": report.total_amount,
            "finding_count": report.finding_count,
            "risk_level": report.risk_level,
            "findings": [],
            "risk_scores": report.risk_scores
        }
        html_path = f"data/reports/dashboard_{state.get('session_id', 'latest')}.html"
        os.makedirs("data/reports", exist_ok=True)
        RichReportGenerator.generate_html_report(report_data, html_path)
        logger.success(f"📊 可视化仪表盘已生成: {html_path}")

        from app.expert_bridge import expert_bridge
        await expert_bridge.push_for_scoring(report_data, f"file:///{os.path.abspath(html_path)}")
    except Exception as ve:
        logger.warning(f"可视化渲染跳过: {ve}")

    return {"structured_report": report, "messages": [final_msg]}


async def consolidator_node(state: AuditState, config: RunnableConfig):
    """[整合节点]：将成功的审计路径固化到语义经验库中"""
    fb = state.get("audit_feedback")
    if fb and fb.decision == "PASS":
        tasks = state.get("tasks", [])
        sql = state.get("sql_query", "")
        # [ISS-009 级联修复] 安全提取用户输入，兼容 tuple ("user", text) 和 HumanMessage 两种格式
        _first_msg = state["messages"][0] if state.get("messages") else None
        if isinstance(_first_msg, tuple):
            user_input = _first_msg[1] if len(_first_msg) > 1 else ""
        else:
            user_input = getattr(_first_msg, "content", "") if _first_msg else ""
        # 优先从 metadata 读取（Fast Route 路径更可靠）
        user_input = (state.get("metadata") or {}).get("user_question") or user_input

        
        if tasks and sql:
            # [V57.1 重大修复] 缓存执行验证门控：
            # 只有 SQL 真实执行成功（无 error_log）且有数据返回，才允许写入缓存
            # 这杜绝了"带病入缓存"：错误表名/失败查询被永久固化导致反复命中错误结果
            has_error = bool(state.get("error_log"))
            has_data  = bool(state.get("raw_data", "").strip()) and "查询失败" not in str(state.get("raw_data", ""))
            
            if has_error or not has_data:
                logger.warning(f"🚫 [CACHE GUARD] SQL 未通过验证门控，拒绝写入缓存 (error={has_error}, data={has_data})")
            else:
                # 语义级经验固化 (FAISS)
                experience_manager.save_audit_experience(tasks, sql)
                # [V48.0 Token 终极优化] 精准 SQL 缓存持久化
                if user_input:
                    from app.semantic_memory import sql_cache_manager
                    sql_cache_manager.save(user_input, sql)
                    logger.success(f"✅ [CACHE SAVE] SQL 验证通过，已写入语义缓存")
    return {}

# ============================================================
# 4. 路由逻辑（V59.3 架构降维）
# ============================================================

def route_post_exec(state: AuditState) -> str:
    """SQLEXEC 后的路由：出错则重试，成功则进入 AUDITOR"""
    if state.get("error_log") and state.get("retry_count", 0) < MAX_RETRIES:
        return "SQLEXEC"  # 重试
    return "AUDITOR"  # 正常路径（包括达到重试上限后强制进入）

def route_post_audit(state: AuditState) -> str:
    """AUDITOR 后的路由：一律进入 CONSOLIDATOR（不再循环回 SQLEXEC）"""
    return "CONSOLIDATOR"

# ============================================================
# 5. 图编译（V59.3 线性托扑）
# ============================================================

def build_graph():
    """
    [V59.3] 线性工作流切换：移除 CRITIC 循环节点

    旧拓扑（可能无限循环）:
        PLANNER → SQLEXEC ↺(重试环) → AUDITOR → CRITIC ↺(取证环) → CONSOLIDATOR → REPORTER

    新拓扑（绹寻可预测）:
        PLANNER → SQLEXEC ↺(限MAX_RETRIES次) → AUDITOR → CONSOLIDATOR → REPORTER → END
    """
    workflow = StateGraph(AuditState)
    workflow.add_node("PLANNER", planner_node)
    workflow.add_node("SQLEXEC", sqlexec_node)
    workflow.add_node("AUDITOR", auditor_node)
    workflow.add_node("REPORTER", reporter_node)
    workflow.add_node("CONSOLIDATOR", consolidator_node)

    workflow.set_entry_point("PLANNER")
    workflow.add_edge("PLANNER", "SQLEXEC")
    workflow.add_conditional_edges(
        "SQLEXEC", route_post_exec,
        {"SQLEXEC": "SQLEXEC", "AUDITOR": "AUDITOR"}
    )
    workflow.add_conditional_edges(
        "AUDITOR", route_post_audit,
        {"CONSOLIDATOR": "CONSOLIDATOR"}
    )
    workflow.add_edge("CONSOLIDATOR", "REPORTER")
    workflow.add_edge("REPORTER", END)
    return workflow.compile()

# 全局编译好的工作流
workflow = build_graph()

class AgentGraph:
    def __init__(self, model_id: str = None): self.model_id = model_id
    def compile(self, checkpointer=None): return workflow

def _record_usage_with_budget(role: str, response: Any, model_id: str, prompt: Any = ""):
    usage_tracker.record_usage(model_id, 0, 0, prompt=prompt, response_text=str(getattr(response, "content", "")))
