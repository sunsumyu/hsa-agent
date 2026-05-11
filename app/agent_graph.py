import operator
import re
from typing import Annotated, Sequence, TypedDict, Dict, List, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
import app.logging_config # [V41.6] 物理链路可跳转配置
import asyncio
import sys

from app.usage_tracker import usage_tracker
from app.compressor import trace_compressor
from app.model_manager import model_manager
from app.neo4j_manager import field_kg, neo4j_manager
from app.prompts import PLANNER_PROMPT, CODER_PROMPT, ANALYST_PROMPT, REPORTER_PROMPT, AUDITOR_PROMPT
# [重构 V90.0] 分层 State + 领域 Schema 单一事实源
from app.core.state import (
    AuditState as _LayeredAuditState,
    AuditFinding as _LayeredAuditFinding,
    AuditReport as _LayeredAuditReport,
    AuditFeedback as _LayeredAuditFeedback,
)
from app.core.schema_registry import schema_registry
from app.tools import execute_audit_sql, get_table_schema, list_tables, search_expert_knowledge, query_fraud_ring
from app.skills import MedicalSchemaSkill, RuleExecutionSkill, SQLSafeExecutionSkill
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
# [重构 V90.0] 已迁移到 app.core.state — 此处仅做别名导出保持向后兼容
AuditFinding = _LayeredAuditFinding
AuditReport = _LayeredAuditReport
AuditFeedback = _LayeredAuditFeedback

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
    methodology: str             # [V59.3] 审计口径/方法论说明，记录 SQL 背后的业务逻辑定义
    temp_table: Optional[str]    # [V65.0] 联邦侧载产生的临时表名



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
    """
    [V66.0] 规划节点：实现语义路由逻辑。
    """
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
    import os as _os
    disable_cache = _os.getenv("DISABLE_AUDIT_CACHE", "false").lower() == "true"
    cached_sql = None if disable_cache else sql_cache_manager.search(user_input)
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
                "extra_filters": route.extra_filters,
                "user_question": user_input,  # [ISS-009 Fix] 保存原始问题供 Reporter 使用
            },
            "retry_count": 0,
            "execution_trace": trace,
            "messages": [] # [V65.7] 修复重复合并 Bug：不再返回旧消息，Reducer 会自动保留原状态
        }

    # ── [V47.3] LLM 推理路径（仅未知/复杂类任务）───────────────────
    complexity = model_manager.classify_complexity_locally(user_input)
    logger.info(f"💡 [ROUTER] 本地语义路由决策结果: {complexity}")

    role = "planner_heavy" if complexity == "HIGH" else "planner_light"
    llm, actual_model = await model_manager.get_llm_by_role(role, retry_count=state.get("retry_count", 0), config=config)

    mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), user_input)
    
    # 获取图谱本体
    ontology = neo4j_manager.get_ontology()

    # ── [V67.5] 注入任务相关的精准 Schema 片段（M4 注入器）──────────
    schema_hint = _schema_injector.inject(user_question=user_input, top_k=6)
    
    prompt_template = get_langfuse_prompt("planner-audit-v1", fallback=PLANNER_PROMPT)
    prompt = prompt_template.format_messages(
        messages=state["messages"], 
        experiences=mem_context, 
        ontology=ontology,
        schema_info=schema_hint
    )
    obs_config = build_obs_config(config, role, state)
    logger.debug(f">>> [执行期诊断] 节点角色: {role} | LLM对象: {llm} | 实际模型ID: {actual_model}")
    response = await llm.ainvoke(prompt, config=obs_config)
    _record_usage_with_budget(role, response, actual_model, prompt=prompt)
    content = str(response.content)
    cognitive_memory_manager.add_message(state.get("session_id", "default"), response)

    # [V65.0 POE] 结构化解析方法论与任务清单
    methodology = ""
    tasks = []
    
    if "### METHODOLOGY" in content:
        parts = content.split("### TASKS")
        meth_part = parts[0].replace("### METHODOLOGY", "").strip()
        methodology = meth_part
        if len(parts) > 1:
            task_part = parts[1].strip()
            tasks = [re.sub(r'^[\-\*123\.]\s*', '', line).strip() for line in task_part.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3."))]
    else:
        # 兼容旧格式
        tasks = [re.sub(r'^[\-\*123\.]\s*', '', line).strip() for line in content.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3."))]

    return {
        "tasks": tasks[:3], 
        "methodology": methodology,
        "messages": [response], 
        "retry_count": 0, 
        "complexity": complexity
    }

async def sqlexec_node(state: AuditState, config: RunnableConfig):
    """
    [工业级 Skills 节点] 完全基于 Tool Calling 调用独立封装的 Skills。
    """
    from app.skills import MedicalSchemaSkill, RuleExecutionSkill, SQLSafeExecutionSkill, FederatedAuditSkill
    retry = state.get("retry_count", 0)
    if retry >= MAX_RETRIES:
        logger.error(f"🛑 [SQLEXEC] 达到重试上限，强制熔断并汇报失败。")
        return {
            "raw_data": "【审计异常】由于系统未能生成有效逻辑，任务已强制终止。",
            "sql_query": state.get("sql_query", "-- 多次尝试执行失败，未保留最终有效 SQL"),
            "methodology": state.get("methodology", ""),
            "sql_validated": True,
            "error_log": "REACHED_MAX_RETRIES"
        }

    # 优先走 Fast Route
    fast_route_id = (state.get("metadata") or {}).get("fast_route_id")
    if fast_route_id:
        logger.success(f"🚀 [FAST_EXEC] Fast Route 命中，直接执行 Skill")
        try:
            skill = RuleExecutionSkill()
            extra_filters = (state.get("metadata") or {}).get("extra_filters")
            res = await skill._arun(fast_route_id, extra_filters=extra_filters)
            if "error" in res:
                raise ValueError(f"FastRoute 算子内部执行失败: {res['error']}")
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
            # [V65.0 POE] 自动采样降噪：防止海量数据撑爆上下文
            if isinstance(raw_evidence, list) and len(raw_evidence) > 50:
                logger.info(f"⚡ [PRUNING] 原始数据量过大 ({len(raw_evidence)}条)，执行物理采样备份，仅保留 50 条证据样本。")
                sample_evidence = raw_evidence[:50]
            else:
                sample_evidence = raw_evidence

            result_str = _j.dumps(sample_evidence, ensure_ascii=False, cls=_AuditEncoder) if isinstance(sample_evidence, list) else str(sample_evidence)
            
            return {
                "raw_data": result_str,
                "sql_query": res.get("sql_logic", f"-- FastRoute: {fast_route_id}"),
                "methodology": res.get("methodology", ""),
                "sql_validated": True,
                "error_log": None,
                "execution_trace": trace,
            }
        except Exception as e:
            logger.warning(f"⚠️ [FAST_EXEC] 执行异常: {e}")
            state.get("metadata", {}).pop("fast_route_id", None)

    logger.info(f">>> [SKILLS] LLM 智能调度 Skills... (尝试 {retry + 1}/3)")
    llm, actual_model = await model_manager.get_llm_by_role("coder", retry_count=retry, config=config)
    
    tools = [MedicalSchemaSkill(), RuleExecutionSkill(), SQLSafeExecutionSkill(), FederatedAuditSkill(), query_fraud_ring]
    llm_with_tools = llm.bind_tools(tools)
    
    tasks_list = state.get("tasks", [])
    mem_context = cognitive_memory_manager.recall_context(state.get("session_id", "default"), "\n".join(tasks_list))
    
    # 获取图谱本体
    ontology = neo4j_manager.get_ontology()
    
    # ── [V67.5] 精准 Schema 注入：根据子任务召回物理字段 ─────────────
    task_str = " ".join(tasks_list)
    schema_hint = _schema_injector.inject(user_question=task_str, top_k=10)
    
    prompt = CODER_PROMPT.format_messages(
        messages=state["messages"], 
        ontology=ontology,
        schema_info=schema_hint,
        methodology=state.get("methodology", ""),
        tasks="\n".join(tasks_list), 
        experiences=mem_context
    )
    
    if retry > 0 and state.get("error_log"):
        prompt.append(HumanMessage(content=f"上一轮执行失败，原因：{state['error_log']}\n请修正参数并重新调用工具。"))
    
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
        sql_logics = []
        methodologies = []
        tool_traces = []
        has_error = False
        error_msg = ""
        
        for t_call, res in results:
            if res is not None:
                tool_msg = ToolMessage(content=str(res), tool_call_id=t_call["id"])
                tool_msgs.append(tool_msg)
                
                if isinstance(res, dict):
                    if "trace_hint" in res:
                        tool_traces.append(res["trace_hint"])
                    if "sql_logic" in res:
                        sql_logics.append(res["sql_logic"])
                    if "methodology" in res:
                        methodologies.append(res["methodology"])
                    if "temp_table" in res:
                        state["temp_table"] = res["temp_table"]
                        
                    if res.get("status") == "ERROR" or "error_message" in res:
                        has_error = True
                        error_msg = res.get("error_message") or res.get("error")
                    else:
                        # [V95.0] 只有真正的业务数据才进入证据链
                        if "records_sample" in res:
                            raw_data_list.append(str(res["records_sample"]))
                        if "raw_evidence" in res:
                            raw_data_list.append(str(res["raw_evidence"]))
                else:
                    # [V95.0] 拦截非字典类型的工具返回（如 schema 描述），防止污染证据链
                    # 仅当工具名包含执行意图时才作为潜在数据加入
                    tool_name = t_call.get("name", "").lower()
                    if "sql" in tool_name or "query" in tool_name:
                        raw_data_list.append(str(res))

        trace = list(state.get("execution_trace") or [])
        for hint in tool_traces:
            trace = _append_trace({"execution_trace": trace}, hint)

        combined_sql = "\n---\n".join(sql_logics) if sql_logics else ""
        combined_meth = "\n\n".join(methodologies) if methodologies else ""

        if has_error:
            logger.warning(f"Skill 报错: {error_msg}")
            return {
                "error_log": error_msg,
                "sql_query": combined_sql,
                "methodology": combined_meth,
                "messages": [response] + tool_msgs,
                "retry_count": retry + 1,
                "execution_trace": trace,
                "temp_table": state.get("temp_table")
            }

        combined_raw = "\n---\n".join(raw_data_list)
        
        return {
            "raw_data": combined_raw,
            "sql_query": combined_sql,
            "methodology": combined_meth,
            "messages": [response] + tool_msgs,
            "retry_count": retry + 1,
            "sql_validated": True,
            "error_log": None,
            "execution_trace": trace,
            "temp_table": state.get("temp_table")
        }
    
    # 无工具调用，尝试解析内容
    return {
        "error_log": "Agent did not output a tool call.",
        "messages": [response],
        "retry_count": retry + 1
    }

async def critic_node(state: AuditState, config: RunnableConfig):
    """[V65.0 POE] 自愈节点：分析取证失败原因并给出修复指令"""
    retry = state.get("retry_count", 0)
    logger.warning(f"🕵️ [CRITIC] 正在诊断执行偏差... (尝试 {retry}/3)")
    
    llm, _ = await model_manager.get_llm_by_role("reporter", config=config)
    
    from app.prompts import CRITIC_PROMPT
    prompt = CRITIC_PROMPT.format_messages(
        methodology=state.get("methodology", "未定义协议"),
        raw_data=state.get("raw_data", "无数据"),
        error_log=state.get("error_log", "无报错日志"),
        messages=state["messages"]
    )
    
    response = await llm.ainvoke(prompt)
    feedback = str(response.content).strip()
    
    logger.info(f"💡 [CRITIC] 诊断建议: {feedback}")
    
    return {
        "error_log": f"[CRITIC 反馈] {feedback}",
        "messages": [response]
    }

async def reporter_node(state: AuditState, config: RunnableConfig):
    """[V65.0 POE] 降噪版报告渲染器：执行状态修剪，防止上下文膨胀。"""
    logger.info(">>> [REPORTER] 正在执行状态降噪并准备渲染报告...")
    
    # ── [V65.0 POE] 状态修剪 (State Pruning) ──────────────────────────
    # 剔除所有的中间错误日志和非必要的中间尝试轨迹，只保留最终确定的审计信息
    pruned_messages = []
    for msg in state.get("messages", []):
        # 仅保留用户输入、最终执行成功的工具调用、以及 Critic 的核心诊断建议
        # 过滤掉过于冗长的错误堆栈消息
        if "error" in str(msg).lower() and "fail" in str(msg).lower() and len(str(msg)) > 500:
            continue
        pruned_messages.append(msg)
    
    from app.booster import booster
    import json as _json

    # ── Step 1: 物理去污 ─────────────────────────────────────────
    raw_data_str = state.get("raw_data", "")
    if isinstance(raw_data_str, str):
        clean_data = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_data_str)
        clean_data = re.sub(r'\\x[0-9a-fA-F]{2}', '', clean_data)
    else:
        clean_data = str(raw_data_str)

    from app.booster import booster, DataExtractionError

    try:
        hard_sum, hard_count, _ = booster.calculate_hard_metrics(clean_data)
    except DataExtractionError as e:
        logger.error(f"🚨 [State Desync] 强约束拦截：数据解析层熔断 -> {e}")
        # 【V62.0 状态单向约束】如果取不到真实数据，直接把错误推回给状态机，绝对不能进入 LLM 结论生成
        return {
            "error_log": f"数据解析失败: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
            # [不再兜底 0，而是生成显式的错误报告]
            "structured_report": AuditReport(
                summary="❌ [系统级故障] 证据提取失败。上游物理探针未能传递合法的数据载荷，出于安全隔离策略，终止报告渲染。",
                findings=[],
                total_amount=0.0,
                finding_count=0,
                risk_level="高"
            )
        }

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
    methodology = state.get("methodology", "")
    execution_trace = list(state.get("execution_trace") or [])

    # ── Step 4: 调用 LLM 只生成第四章"核查结论"（约 150~300 字）───────
    llm_conclusion = ""
    try:
        llm, _ = await model_manager.get_llm_by_role("reporter", config=config)

        # [V59.1] 极简 Conclusion Prompt：强调核查广度与方法的透明度
        CONCLUSION_PROMPT = (
            "你是一名极其严谨的医保基金稽核专家。根据以下审计取证信息，撰写 150~300 字的「核查结论」。\n"
            "要求：\n"
            "1. 结论必须明确（发现或未发现违规）。\n"
            "2. 必须引用下方的“审计方法论”中的核心判定标准，展示核查的专业性。\n"
            "3. 如果发现条数为 0，必须说明核查已穿透相关结算明细，验证了业务逻辑的完整性，确保无遗漏。\n"
            "4. 给出具有可操作性的后续整改或监测建议。\n\n"
            f"审计任务：{user_question[:300]}\n\n"
            f"审计方法论：{methodology[:500]}\n\n"
            f"执行轨迹：{'; '.join(execution_trace[-3:]) if execution_trace else '已完成物理数据核查'}\n\n"
            f"数据摘要：共穿透扫描相关记录 {hard_count} 条，涉及金额 ¥{hard_sum:,.2f}"
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
        methodology=methodology,
        table_info=f"{schema_registry.get_main_table()}（{schema_registry.get_table(schema_registry.get_main_table()).alias if schema_registry.get_table(schema_registry.get_main_table()) else '全量结算明细'}）",
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
        findings=raw_data_list,
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
            "findings": raw_data_list[:20], # 仪表盘仅展示前20条
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

# [重构 V90.0] 删除旧的简陋 route_post_exec / route_post_audit
# 原因: build_graph() 内定义了嵌套的同名高级版本 (含契约检查), 会遮蔽模块级版本;
# 但 get_graph_executor() 却引用模块级旧版, 导致两条编译路径行为不一致 (Bug)。
# 新版: 将高级路由提升为模块级 _route_sqlexec_post, 单一实现, 两个工厂共用。


def _route_sqlexec_post(state: AuditState) -> str:
    """
    SQLEXEC 后的增强型路由:
    
      - 内部推理环路: 如果 Coder 刚调了工具 (last_msg 是 ToolMessage 或带 tool_calls),
        继续留在 SQLEXEC 做下一步思考 (未达 MAX_RETRIES)。
      - 契约检查: methodology 要求数值但 raw_data 里没数字 -> 判定契约失效。
      - 出错 / 契约失效 且未达上限 -> 进 CRITIC 自愈。
      - 其他 -> 进 CONSOLIDATOR。
    """
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    # 1. 内部推理环路
    if isinstance(last_msg, ToolMessage) or (
        not isinstance(last_msg, tuple) and getattr(last_msg, "tool_calls", None)
    ):
        if state.get("retry_count", 0) < MAX_RETRIES:
            return "SQLEXEC"

    # 2. 契约检查
    raw_data = state.get("raw_data", "")
    has_error = bool(state.get("error_log"))
    contract_violation = False
    methodology = str(state.get("methodology", ""))
    if "### METHODOLOGY" in methodology and (
        "金额" in methodology or "费用" in methodology or "数值" in methodology
    ):
        numbers = re.findall(r"\d+\.\d+|\d{4,}", raw_data)
        if not numbers:
            contract_violation = True
            logger.warning(
                "🚨 [CONTRACT] 检测到数据契约失效：审计口径要求数值，但取证载荷为空或无显著指标"
            )

    if (has_error or contract_violation) and state.get("retry_count", 0) < MAX_RETRIES:
        return "CRITIC"
    return "CONSOLIDATOR"


def _build_workflow_skeleton() -> StateGraph:
    """
    构建工作流拓扑 (不含 compile)。build_graph 和 get_graph_executor 共用。
    
    拓扑: PLANNER -> SQLEXEC -> (route) -> {SQLEXEC | CRITIC | CONSOLIDATOR}
          CRITIC  -> SQLEXEC
          CONSOLIDATOR -> REPORTER -> END
    """
    wf = StateGraph(AuditState)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("SQLEXEC", sqlexec_node)
    wf.add_node("CRITIC", critic_node)
    wf.add_node("REPORTER", reporter_node)
    wf.add_node("CONSOLIDATOR", consolidator_node)

    wf.set_entry_point("PLANNER")
    wf.add_edge("PLANNER", "SQLEXEC")
    wf.add_conditional_edges(
        "SQLEXEC",
        _route_sqlexec_post,
        {
            "SQLEXEC": "SQLEXEC",
            "CRITIC": "CRITIC",
            "CONSOLIDATOR": "CONSOLIDATOR",
        },
    )
    wf.add_edge("CRITIC", "SQLEXEC")
    wf.add_edge("CONSOLIDATOR", "REPORTER")
    wf.add_edge("REPORTER", END)
    return wf

# ============================================================
# 5. 图编译（V59.3 线性托扑）
# ============================================================

def build_graph():
    """
    [V65.0 POE 拓扑] 增强型线性工作流 + 自愈环路
    PLANNER → SQLEXEC → (Contract Check) → CRITIC ↺ → CONSOLIDATOR → REPORTER → END
    
    [重构 V90.0] 拓扑委托给 _build_workflow_skeleton, 保证和 get_graph_executor 行为一致。
    """
    return _build_workflow_skeleton().compile()

# 全局编译好的工作流
workflow = build_graph()

# ────────────────────────────────────────────────────────────────
# [重构 V90.0] get_graph_executor — main.py 期望存在的导出
# ────────────────────────────────────────────────────────────────
# 历史包袱: main.py 多处调用 get_graph_executor(checkpointer=, model_id=)
# 期望返回 (executor, resolved_model_id) 元组。
# 之前此函数从未导出过, 导致 main.py import 时 ImportError。
# ────────────────────────────────────────────────────────────────

_EXECUTOR_CACHE: Dict[str, Any] = {}


def get_graph_executor(checkpointer=None, model_id: Optional[str] = None):
    """
    获取 LangGraph 执行器单例。
    
    Args:
        checkpointer: AsyncSqliteSaver 实例 (用于状态持久化)
        model_id: 客户端指定的模型 ID (用于动态路由)
    
    Returns:
        Tuple[CompiledGraph, str]: (执行器, 实际使用的模型 ID)
    """
    cache_key = f"{id(checkpointer)}_{model_id or 'default'}"

    if cache_key in _EXECUTOR_CACHE:
        return _EXECUTOR_CACHE[cache_key], (model_id or "default")

    # [重构 V90.0] 拓扑由 _build_workflow_skeleton 统一定义, 保证行为一致
    if checkpointer is not None:
        executor = _build_workflow_skeleton().compile(checkpointer=checkpointer)
    else:
        executor = workflow

    _EXECUTOR_CACHE[cache_key] = executor
    resolved_id = model_id or "default"
    logger.info(f"[GraphExecutor] cache_key={cache_key} resolved_model_id={resolved_id}")
    return executor, resolved_id


class AgentGraph:
    def __init__(self, model_id: str = None): self.model_id = model_id
    def compile(self, checkpointer=None): return workflow

def _record_usage_with_budget(role: str, response: Any, model_id: str, prompt: Any = ""):
    usage_tracker.record_usage(model_id, 0, 0, prompt=prompt, response_text=str(getattr(response, "content", "")))
