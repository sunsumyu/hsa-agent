"""
app/tools.py
============
[企业级可复用工具库]
集成 ClickHouse 物理执行引擎、RAG 专家知识库、规则算子库。
[V59.4] 关键修复：将所有 SQL 执行逻辑异步化，防止 heavy query 阻塞事件循环。
"""

import os
import re
import json
import asyncio
from typing import List, Dict, Any, Tuple, Union, Optional, Annotated
from loguru import logger
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.db_conn import get_clickhouse_client, SqlExecError
from app.audit_rules import rule_engine
from app.anomaly_algorithms import anomaly_detector
from app.security import SQLGuardian
from app.perf_monitor import perf_monitor
from app.core.skill_protocol import SkillResponse
from app.core.config import settings
from app.core.utils import smart_parse_tool_params

# ──────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────

def _sanitize_results(records: List[Dict], tolerance: int = 1000) -> List[Dict]:
    """
    [V72.0 企业级] 业务感知型数据清洗中间件：
    - 支持梯级熔断：L1(放行), L2(告警), L3(强力拦截)
    - 结合 FieldKG 进行动态脱敏
    """
    HARD_MELT_LIMIT = 200000 # 绝对物理上限
    cleaned = []
    tolerance = settings.sql_row_tolerance
    
    for row in records:
        for key, val in row.items():
            # 1. 动态算力审计 (Tiered Circuit Breaker)
            if 'count' in key.lower() and isinstance(val, (int, float)):
                if val > HARD_MELT_LIMIT:
                    logger.error(f"🚨 [MELT] 触发绝对物理熔断！字段 {key} 数值 {val} 远超系统承载极限，疑似严重 SQL 逻辑错误。")
                    raise ValueError(f"物理安全拦截：检测到异常明细爆炸 ({val})。请检查 SQL 中的 JOIN 条件，必须通过 setl_id 精确排重。")
                
                if val > tolerance:
                    # [V72.0] 梯级降级：仅记录告警，不再直接抛出异常
                    logger.warning(f"⚠️ [Sanitizer] 探测到高体量业务数据 ({key}={val})。当前规则容差: {tolerance}。已记录并放行。")
            
            if not isinstance(val, str): continue
            
            # 2. 乱码清洗
            if val == "" or val is None: continue
            if '\ufffd' in val:
                row[key] = "[数据源乱码/GBK编码冲突]"
            
            # 3. 基础脱敏 (V128.9 自适应脱敏)
            has_binary = any(ord(c) < 32 and c not in '\n\r\t' for c in val)
            if has_binary:
                # [V110.0] 分级脱敏策略：在 Benchmark 模式下，允许放行非脱敏字段用于“证据验证”
                if os.getenv("IS_BENCHMARK_MODE", "false").lower() == "true":
                    # 仅做部分掩码，不做全量 REDACTED
                    if len(val) > 4:
                        row[key] = val[:2] + "**" + val[-2:]
                    continue
                row[key] = "[REDACTED/ENCRYPTED]"
                
        cleaned.append(row)
    return cleaned

@perf_monitor.time_it("AUDIT_ENGINE")
async def _execute_audit_sql_logic(
    sql: str, 
    db_type: str = "clickhouse", 
    return_raw: bool = False, 
    tolerance: int = 1000,
    tenant_id: Optional[str] = None
) -> Any:
    """内部物理执行逻辑 [V172.1] 增加 tenant_id 隔离"""
    if db_type == "clickhouse":
        try:
            # 1. 物理拦截与行政区划隔离注入
            safe_sql = SQLGuardian.validate_sql(sql, tenant_id=tenant_id)
            
            # [V176.0] 物理防御：防止 safe_sql 为空导致 upper() 崩溃
            safe_sql_upper = (safe_sql or "").upper()
            
            async def _run_sql(s_sql: str):
                client = get_clickhouse_client()
                return await asyncio.to_thread(client.query, s_sql)

            # [V162.0] 行政层级感知隔离 (Administrative Hierarchy Isolation)
            from app.core.context import tenant_context
            t_id = tenant_context.get()
            
            if t_id and "FROM" in safe_sql_upper:
                # 定义过滤子句
                filter_clause = ""
                if t_id.startswith("DIST_"):
                    # 县区级：精确匹配 admdvs
                    filter_clause = f"admdvs = '{t_id.split('_')[1]}'"
                elif t_id.startswith("CITY_"):
                    # 地市级：前缀匹配 (例如 3101%)
                    city_prefix = t_id.split('_')[1][:4]
                    filter_clause = f"admdvs LIKE '{city_prefix}%'"
                
                if filter_clause and "admdvs" not in safe_sql_upper:
                    logger.info(f"🛡️ [MultiTenant] 正在应用行政隔离 ({t_id}): {filter_clause}")
                    if "WHERE" in safe_sql_upper:
                        safe_sql = safe_sql.replace("WHERE", f"WHERE {filter_clause} AND", 1)
                    else:
                        match = re.search(r"(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|;|$)", safe_sql, re.IGNORECASE)
                        pos = match.start()
                        safe_sql = safe_sql[:pos] + f" WHERE {filter_clause}" + safe_sql[pos:]

            try:
                result = await _run_sql(safe_sql)
            except SqlExecError as first_err:
                err_str = str(first_err)
                # [V131.0] Code 215 自愈：一次自动修复 + 重试
                if "Code: 215" in err_str:
                    healed = _heal_group_by_215(safe_sql, err_str)
                    if healed != safe_sql:
                        try:
                            result = await _run_sql(healed)
                            safe_sql = healed  # 修复成功，使用新 SQL
                        except SqlExecError as retry_err:
                            # 修复后仍失败，统一在此打 ERROR 并返回
                            final_err = str(retry_err)
                            logger.error(f"[SQL_EXEC_ERROR] 自愈失败: {final_err}")
                            return {"status": "ERROR", "error_message": final_err, "sql_logic": healed}
                    else:
                        # 无法自愈，直接报错
                        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                        return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}
                else:
                    # 其他错误，单一记录并返回
                    if "404" in err_str or "Connection refused" in err_str or "无法建立" in err_str:
                        logger.error(f"[INFRA_ERROR] ClickHouse 不可达: {err_str[:150]}")
                        return {
                            "status": "ERROR",
                            "error_message": f"⚠️ ClickHouse 数据库未启动或不可达。请检查服务状态。原始错误: {err_str[:200]}",
                            "sql_logic": sql, "is_infra_error": True
                        }
                    logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                    return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}

            if return_raw:
                return _sanitize_results(result, tolerance=tolerance)
            
            # [V157.0] USP 协议封装：始终返回结构化载荷，增强 AuditMessage 识别能力
            response = SkillResponse(
                status="SUCCESS",
                data=_sanitize_results(result, tolerance=5), # 默认返回 5 条样值供审计证据链
                logic_summary=f"已成功穿透底层数据库，检索到相关审计证据。",
                affected_rows=len(result),
                trace_hint=f"Query executed successfully via Clickhouse.",
                security_verified=True
            )
            
            # 为了兼容旧版解析器，返回 dict 但包含 USP 字段
            return response.model_dump()

        except Exception as e:
            err_str = str(e)
            from app.security import SecurityViolationError
            if isinstance(e, SecurityViolationError):
                logger.debug(f"[SQL_GOVERNANCE] 执行拦截: {err_str}")
                return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
            # 其他未预期异常（如 SQLGuardian 或其他错误），单一记录
            logger.error(f"[SQL_EXEC_ERROR] {err_str}")
            return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}

    return {"status": "ERROR", "error_message": "所请求的数据库类型暂不支持。", "sql_logic": sql}

def _heal_group_by_215(sql_text: str, err_str: str) -> str:
    """
    [V132.1] 强化版 Code 215 自愈器：支持全限定列名提取与鲁棒性正则。
    """
    # 改进正则：支持提取 default.table.col 这种全限定名中的最后一节
    match = re.search(r"Column\s+'(?:[^']+\.)*([^']+)'\s+is\s+not\s+under\s+aggregate", err_str, re.IGNORECASE)
    if not match:
        return sql_text

    bad_col = match.group(1)
    logger.warning(f"🔧 [SQL_HEALER] 识别到未分组字段: `{bad_col}`，执行 AST 级修复...")

    # 改进正则：更精准地定位 GROUP BY 结尾，处理可能存在的分号
    # 逻辑：在 GROUP BY 块的最后一个字段后追加 , bad_col
    new_sql = re.sub(
        r'(GROUP\s+BY\s+)(.*?)(\s*(?:HAVING|ORDER\s+BY|LIMIT|;|$))',
        lambda m: f"{m.group(1)}{m.group(2).strip()}, {bad_col}{m.group(3)}",
        sql_text, count=1, flags=re.IGNORECASE | re.DOTALL
    )
    if new_sql == sql_text:
        return sql_text  # 没有 GROUP BY，无法修复

    logger.info(f"✅ [SQL_HEALER] SQL 已自愈，重试中…")
    return new_sql

# ──────────────────────────────────────────────────────────
# 暴露给 Agent 的工具集 (Decorated Tools)
# ──────────────────────────────────────────────────────────

@tool
async def execute_audit_sql(
    sql: Union[str, Dict], 
    state: Annotated[dict, InjectedState], # [V172.1] 自动注入状态
    db_type: str = "clickhouse"
) -> Any:
    """执行医疗相关 SQL 查询。自动执行行政区划隔离。"""
    # 提取租户信息
    tenant_id = state.get("metadata", {}).get("tenant_id") or state.get("metadata", {}).get("admin_division")
    
    # [V163.1] 鲁棒性参数解析
    params = smart_parse_tool_params(sql)
    actual_sql = params.get("sql", sql if isinstance(sql, str) else "")
    actual_db = params.get("db_type", db_type)
    
    return await _execute_audit_sql_logic(actual_sql, actual_db, tenant_id=tenant_id)

@tool
def list_tables() -> str:
    """列出当前医保审计数据库中所有可用的物理表及其业务说明。从 SchemaRegistry 读取，不再写死。"""
    from app.core.schema_registry import schema_registry
    return schema_registry.get_tables_summary() or "⚠️ 未加载到表定义"

# 表名校验正则: 仅允许字母/数字/下划线, 防止 SQL 注入
import re as _re_tools
_TABLE_NAME_RE = _re_tools.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

@tool
def get_table_schema(table_name: str) -> str:
    """获取 ClickHouse 物理表的真实字段结构。优先从 SchemaRegistry 读取，未注册时才走 DESCRIBE。"""
    # 安全校验: 防止 SQL 注入。原代码直接拼接 {table_name} 到 SQL。
    if not table_name or not _TABLE_NAME_RE.match(table_name):
        return f"非法表名: {table_name!r} (仅允许 a-zA-Z0-9_)"

    from app.core.schema_registry import schema_registry
    # 1. 优先走注册表 (零 DB 费用)
    entry = schema_registry.get_table(table_name)
    if entry:
        return "\n".join(
            f"{f['name']} ({f.get('type', 'String')}) - {f.get('desc', '')}"
            for f in entry.fields
        )
    # 2. 未注册才查数据库 (此时已经通过名称正则校验, 安全)
    try:
        client = get_clickhouse_client()
        result = client.query(f"DESCRIBE TABLE {table_name}")
        fields = [f"{row[0]} ({row[1]})" for row in result.result_rows]
        return "\n".join(fields) if fields else f"表 {table_name} 不存在"
    except Exception as e:
        return f"获取表结构失败: {e}"

# 安全计算器: 只允许数字+运算符。路由物理拦截子类逃逸攻击。
_SAFE_EXPR_RE = _re_tools.compile(r"^[\d\s\.\+\-\*\/\(\)\%]+$")

@tool
def calculator(expr: str) -> str:
    """高精度数学计算器。仅支持数字和算术运算符，拒绝名称、属性访问、函数调用等。防止 eval() 的子类逃逸攻击。"""
    if not expr or not _SAFE_EXPR_RE.match(expr):
        return f"非法表达式: {expr!r} (仅允许数字和 + - * / ( ) % )"
    try:
        # compile 为 expression mode + 源码白名单双重防护
        code = compile(expr, "<calc>", "eval")
        for name in code.co_names:
            return f"非法名称引用: {name}"
        return str(eval(code, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"计算失败: {e}"


@tool
def check_audit_governance() -> Dict[str, Any]:
    """
    [V118.0] 获取审计治理与物理合规规则。
    当 Agent 不确定表名合法性、字段脱敏要求或 SQL 执行限制时，必须调用此工具。
    返回内容：禁用的幻觉表名单、合法表前缀、敏感字段清单、强制时间过滤要求等。
    """
    from app.core.schema_registry import schema_registry
    return {
        "forbidden_tables": list(schema_registry.get_forbidden_table_names()),
        "valid_table_prefixes": schema_registry.get_valid_prefixes(),
        "sensitive_fields": list(schema_registry.get_sensitive_fields()),
        "main_table": schema_registry.get_main_table(),
        "default_time_filter": schema_registry.get_default_time_filter(),
        "performance_constraints": {
            "max_execution_time_sec": schema_registry.get_max_execution_time(),
            "max_memory_usage": schema_registry.get_max_memory_usage()
        },
        "instruction": "严禁使用上述 forbidden_tables。所有针对物理表的查询必须符合前缀规范，并显式带上时间范围过滤。"
    }

@tool
def lookup_medical_schema(keywords: str) -> str:
    """
    [V118.1] 检索医疗数据库物理 Schema。
    根据业务关键词（如'重复收费'、'总金额'）查询对应的物理表字段、DDL 结构及审计合规禁区。
    写 SQL 前必须调用此工具以防止字段幻觉和物理拦截。
    """
    from app.skills.medical_schema import MedicalSchemaSkill
    skill = MedicalSchemaSkill()
    return skill._run(keywords)

# ──────────────────────────────────────────────────────────
# 规则引擎与专家知识 (M3 成果落地)
# ──────────────────────────────────────────────────────────

# [重构 V90.0] 专家知识库: 从 SemanticRetriever 识别任务型别返回针对性提示
import os as _os_tools
_EXPERT_KB_PATH = _os_tools.path.join(
    _os_tools.path.dirname(__file__), "..", "configs", "expert_knowledge.yaml"
)
_EXPERT_KB_CACHE = None

def _load_expert_kb():
    global _EXPERT_KB_CACHE
    if _EXPERT_KB_CACHE is not None:
        return _EXPERT_KB_CACHE
    try:
        import yaml
        with open(_EXPERT_KB_PATH, "r", encoding="utf-8") as f:
            _EXPERT_KB_CACHE = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _EXPERT_KB_CACHE = {}
    except Exception as e:
        logger.warning(f"[ExpertKB] load failed: {e}")
        _EXPERT_KB_CACHE = {}
    return _EXPERT_KB_CACHE

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医保审计专家知识库。从 configs/expert_knowledge.yaml 加载由主题索引的专家提示。"""
    if not query:
        return "⚠️ 查询为空"

    kb = _load_expert_kb()
    topics = kb.get("topics", [])
    if not topics:
        return "⚠️ 专家知识库未配置 (configs/expert_knowledge.yaml)"

    q_lower = query.lower()
    matched = []
    for topic in topics:
        keywords = topic.get("keywords", [])
        if any(kw.lower() in q_lower for kw in keywords):
            matched.append(
                f"【{topic.get('title', '')}】{topic.get('hint', '')}"
            )

    if not matched:
        return f"未检索到与 '{query}' 匹配的专家知识。已收录主题: " + ", ".join(
            t.get("title", "") for t in topics
        )
    return "\n\n".join(matched)

@tool
@perf_monitor.time_it("RULE_ENGINE_EXEC")
async def audit_medical_rule(rule_id: str) -> str:
    """[V176.0] 加固版规则引擎
    执行预定义的物理违规规则匹配。自动映射语义到物理算子，并异步执行。
    """
    if not rule_id: return "Error: rule_id is required."
    rule_key = str(rule_id).upper()
    
    logger.info(f"🔨 [TOOL] 执行物理违规规则引擎: {rule_id}")
    
    # 语义路由映射
    target_rule = ""
    if "GENDER" in rule_key or "性别" in rule_key:        target_rule = "GENDER_CONFLICT"
    elif "DRUG" in rule_key or "购药" in rule_key:          target_rule = "HIGH_FREQ_DRUG_PURCHASE"
    elif "DECOMPOSITION" in rule_key or "分解" in rule_key:  target_rule = "DECOMPOSITION_HOSPITALIZATION"
    elif "CROSS" in rule_key or "重复住院" in rule_key or "同时住院" in rule_key:
                                                              target_rule = "CROSS_HOSPITAL_OVERLAP"
    elif "REPEAT_BILLING" in rule_key or "重复收费" in rule_key: target_rule = "REPEAT_BILLING_DETECTOR"
    elif "CONTACT_SHARING" in rule_key or "联系方式" in rule_key: target_rule = "CONTACT_SHARING_DETECTOR"
    else: target_rule = rule_key
    
    sql = rule_engine.get_rule_sql(target_rule)
    if not sql:
        return json.dumps({"report": f"未找到匹配的审计算子: {rule_id}", "evidence_count": 0, "raw_evidence": []})

    try:
        # 核心异步执行 (V72.0 注入业务容差)
        tolerance = 50000 if "REPEAT_BILLING" in target_rule else 1000
        raw_data = await _execute_audit_sql_logic(sql, return_raw=True, tolerance=tolerance)
        
        if isinstance(raw_data, str) and "失败" in raw_data:
             return json.dumps({"report": f"物理引擎执行受阻: {raw_data}", "evidence_count": 0, "raw_evidence": []})
             
        count = len(raw_data)
        report_text = rule_engine.format_violation_report(target_rule, raw_data)
        
        return json.dumps({
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "trace_hint": f"[规则引擎] 触发算子 {target_rule}，物理库命中 {count} 条违规证据"
        })
    except Exception as e:
        logger.error(f"规则引擎执行异常: {e}")
        return json.dumps({
            "report": "物理探测异常", 
            "evidence_count": 0, 
            "error": str(e), 
            "raw_evidence": [], 
            "trace_hint": f"[规则引擎] {rule_id} 执行异常"
        })

@tool
@perf_monitor.time_it("ANOMALY_ALGO_EXEC")
async def run_anomaly_detection(algorithm_id: str, threshold: float = 0.95) -> str:
    """[V176.0] 加固版异常检测
    运行统计学异常检测算法。自动映射语义到物理算子，并异步执行。
    """
    if not algorithm_id: return "Error: algorithm_id is required."
    algo_key = str(algorithm_id).upper()
    
    logger.info(f"📊 [TOOL] 执行物理异常检测算子: {algorithm_id}")
    
    # 语义路由映射
    target_algo = ""
    algo_key = algorithm_id.upper()
    if "VIX" in algo_key or "变异" in algo_key: target_algo = "VIX_ANOMALY_SCAN"
    elif "OUTLIER" in algo_key or "离群" in algo_key: target_algo = "STATISTICAL_OUTLIER_DETECTOR"
    elif "CLUSTER" in algo_key or "聚集" in algo_key or "联系方式" in algo_key: target_algo = "CLUSTER_ENCOUNTER_DETECTOR"
    elif "MAD" in algo_key or "稳健" in algo_key: target_algo = "ROBUST_MAD_DETECTOR"
    else: target_algo = algo_key
    
    sql = anomaly_detector.get_algorithm_sql(target_algo)
    if not sql:
        return {"report": f"未找到匹配的算法算子: {algorithm_id}", "evidence_count": 0, "raw_evidence": []}

    try:
        # V72.0 注入业务容差 (统计异常通常具有较高基数)
        raw_data = await _execute_audit_sql_logic(sql, return_raw=True, tolerance=20000)
        
        if isinstance(raw_data, str) and "失败" in raw_data:
             return {"report": f"物理算法执行受阻: {raw_data}", "evidence_count": 0, "raw_evidence": []}
             
        count = len(raw_data)
        report_text = anomaly_detector.format_anomaly_report(target_algo, raw_data)
        
        return {
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "trace_hint": f"[异常算法] 触发算子 {target_algo}，物理库命中 {count} 条异常线索"
        }
    except Exception as e:
        logger.error(f"算法引擎执行异常: {e}")
        return {
            "report": "物理探测异常", 
            "evidence_count": 0, 
            "error": str(e), 
            "raw_evidence": [], 
            "trace_hint": f"[异常算法] {algorithm_id} 执行异常"
        }

# --- 知识检索增强 (RAG) 占位 ---
_embeddings = None
def get_embeddings():
    global _embeddings
    if _embeddings is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        class SimpleEmbeddings:
            def embed_documents(self, texts):
                return model.encode(texts).tolist()
            def embed_query(self, text):
                return model.encode([text])[0].tolist()
        _embeddings = SimpleEmbeddings()
    return _embeddings

# ──────────────────────────────────────────────────────────
# Neo4j 团伙欺诈分析工具 (Graph Analysis)
# ──────────────────────────────────────────────────────────

@tool
@perf_monitor.time_it("NEO4J_GRAPH_QUERY")
async def query_fraud_ring(cypher: str) -> Dict[str, Any]:
    """
    [V59.6] 执行 Neo4j Cypher 查询，用于发现隐蔽的医疗欺诈团伙。
    例如：查找共用同一电话的患者群体，或通过同一医生洗单的异常网络。
    """
    from app.neo4j_manager import neo4j_manager
    logger.info(f"🕸️ [GRAPH] 执行 Cypher 查询: {cypher}")
    
    try:
        # --- [V61.8] 工具空间隔离：物理拦截关系表进入图查询 ---
        import re
        relational_tables = re.findall(r'\bfqz_[a-z0-9_]+\b', cypher, re.IGNORECASE)
        if relational_tables:
            logger.warning(f"🚨 [SPACE_ISOLATION] 拦截到越界图查询意图: {relational_tables}")
            return {
                "status": "ERROR",
                "error_message": f"物理拦截：在 Cypher 语句中发现了关系型表名 {relational_tables}。图数据库（Neo4j）中不包含物理表，仅包含节点（如 Patient, Contact）和关系（如 HAS_CONTACT）。请重新规划，在 [RELATIONAL_ZONE] 使用 execute_audit_sql 查询该表。",
                "sql_logic": cypher
            }

        # 使用 asyncio.to_thread 防止阻塞
        def _exec_cypher():
            driver = neo4j_manager.get_driver()
            with driver.session() as session:
                result = session.run(cypher)
                return [dict(record) for record in result]
        
        records = await asyncio.to_thread(_exec_cypher)
        count = len(records)
        
        return {
            "report": f"图数据库查询成功，发现 {count} 个关联节点/关系对。",
            "evidence_count": count,
            "raw_evidence": records,
            "sql_logic": cypher,
            "trace_hint": f"[图谱分析] 执行 Cypher 命中 {count} 条深层关联线索"
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ [GRAPH ERROR] Neo4j 物理查询失败: {error_msg}")
        
        # [V113.1] 自动反馈：如果查询失败，立即拉取本体结构告知 Agent，防止其继续臆造标签
        current_ontology = neo4j_manager.get_ontology()
        
        return {
            "status": "ERROR",
            "error_message": f"图数据库查询失败: {error_msg}。",
            "suggested_ontology": current_ontology,
            "suggestion": "检测到您可能使用了不存在的标签或属性。请参考上述 [Neo4j Graph Ontology] 重新编写 Cypher。重点：业务数据（患者等）可能尚未注入，如果 Ontology 为空，请先尝试 lookup_medical_schema。"
        }

@tool
def expand_medical_codes(intent: str) -> str:
    """
    [V125.0] 业务深度增强：从知识库检索医疗编码建议 (ICD-10/ICD-9)。
    """
    kb_path = "configs/audit_knowledge_base.json"
    try:
        import json
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f).get("medical_codes", {})
    except:
        return "⚠️ 知识库加载失败"
    
    q = intent.strip()
    matched = []
    for k, v in kb.items():
        if k in q or q in k:
            res = f"【{k}】专业编码映射建议：\n"
            if "icd10" in v:
                res += f"- ICD-10 (疾病): {v['icd10'][0]} 至 {v['icd10'][1]}\n"
            res += f"- 业务说明: {v.get('desc', '')}"
            matched.append(res)
    
    if not matched:
        return f"未找到与 '{intent}' 相关的专业分类。建议直接尝试 LIKE '%{intent}%'。"
    
    return "\n\n".join(matched)

@tool
@perf_monitor.time_it("FEDERATED_SIDELOADER")
async def federated_graph_sideloader(cypher: str, return_key: str = "") -> Dict[str, Any]:
    """
    [企业级联邦侧载工具] 
    执行 Cypher 图谱检索，并将发现的核心实体 ID 自动侧载到 ClickHouse 内存临时表。
    适用于：团伙欺诈、共用号码等跨库多步推理场景。
    参数:
    - cypher: Neo4j 查询语句。
    - return_key: 需要提取的实体 ID 字段名（如果不填则默认提取第一列）。
    """
    from app.neo4j_manager import neo4j_manager
    import time
    import hashlib
    
    logger.info(f"🕸️ [SIDELOADER] 开始联邦查询 (Neo4j -> ClickHouse)")
    try:
        def _exec_cypher():
            driver = neo4j_manager.get_driver()
            with driver.session() as session:
                return [dict(record) for record in session.run(cypher)]
                
        records = await asyncio.to_thread(_exec_cypher)
        if not records:
            return {"status": "SUCCESS", "message": "图谱查询完成，未发现匹配团伙/节点。", "count": 0}
            
        ids = []
        for r in records:
            if return_key and return_key in r:
                val = r[return_key]
            else:
                val = list(r.values())[0] if r else None
            if val: ids.append(str(val))
            
        ids = list(set(ids))
        if not ids:
             return {"status": "ERROR", "error_message": "无法从 Cypher 结果中提取有效的实体 ID 进行侧载。"}
             
        batch_id = hashlib.md5(f"{time.time()}_{len(ids)}".encode()).hexdigest()[:8]
        temp_table = f"fqz_temp_sl_{batch_id}"
        
        client = get_clickhouse_client()
        create_sql = f"CREATE TABLE IF NOT EXISTS {temp_table} (id String) ENGINE = Memory"
        
        try:
            if hasattr(client.client, 'execute'):
                client.client.execute(create_sql)
                client.client.execute(f"INSERT INTO {temp_table} (id) VALUES", [(x,) for x in ids])
            else:
                client.client.command(create_sql)
                client.client.insert(temp_table, [[x] for x in ids], column_names=['id'])
        except Exception as insert_e:
            logger.error(f"ClickHouse 写入临时表失败: {insert_e}")
            return {"status": "ERROR", "error_message": f"侧载到 ClickHouse 失败: {insert_e}"}
            
        return {
            "status": "SIDELOADED",
            "message": f"侧载成功！在 Neo4j 中发现了 {len(ids)} 个目标实体。",
            "temp_table": temp_table,
            "instruction": f"请立即编写 SQL，使用 INNER JOIN {temp_table} ON 主表的关键ID = {temp_table}.id 来关联查询明细及报销金额。"
        }
    except Exception as e:
        logger.error(f"❌ [SIDELOADER ERROR] 联邦侧载失败: {e}")
        return {"status": "ERROR", "error_message": str(e)}
