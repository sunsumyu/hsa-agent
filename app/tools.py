"""
app/tools.py
============
[企业级可复用工具库]
集成 ClickHouse 物理执行引擎、RAG 专家知识库、规则算子库。
[V59.4] 关键修复：将所有 SQL 执行逻辑异步化，防止 heavy query 阻塞事件循环。
"""

import os
import json
import asyncio
from typing import List, Dict, Any, Tuple
from loguru import logger
from langchain_core.tools import tool

from app.db_conn import get_clickhouse_client
from app.audit_rules import rule_engine
from app.anomaly_algorithms import anomaly_detector
from app.security import SQLGuardian

# ──────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────

def _sanitize_results(records: List[Dict], tolerance: int = 1000) -> List[Dict]:
    """
    [V72.0 企业级] 业务感知型数据清洗中间件：
    - 支持梯级熔断：L1(放行), L2(告警), L3(强力拦截)
    - 结合 FieldKG 进行动态脱敏
    """
    HARD_MELT_LIMIT = 200000 # 绝对物理上限，防止笛卡尔积彻底撑爆内存
    cleaned = []
    
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
            
            # 3. 基础脱敏
            has_binary = any(ord(c) < 32 and c not in '\n\r\t' for c in val)
            if has_binary:
                # [V110.0] 分级脱敏策略：在 Benchmark 模式下，允许放行非脱敏字段用于“证据验证”
                if os.getenv("IS_BENCHMARK_MODE", "false").lower() == "true":
                    continue
                row[key] = "[REDACTED/ENCRYPTED]"
                
        cleaned.append(row)
    return cleaned

async def _execute_audit_sql_logic(sql: str, db_type: str = "clickhouse", return_raw: bool = False, tolerance: int = 1000) -> Any:
    """
    [V72.0] 核心执行逻辑：支持业务感知的容差控制
    """
    try:
        safe_sql = SQLGuardian.validate_sql(sql)
        
        if db_type.lower() == "clickhouse":
            client = get_clickhouse_client()
            # result 已经是 List[Dict] (由 CharsetProxy 标准化)
            result = await asyncio.to_thread(client.query, safe_sql)
            
            if return_raw:
                return _sanitize_results(result, tolerance=tolerance)
            return f"查询成功，返回 {len(result)} 条记录。"
            
        return "MySQL 暂不支持在此路径执行。"
    except Exception as e:
        err_str = str(e)
        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
        # [V90.6] 针对基础设施错误给出清晰诊断，避免 LLM 盲目重试
        if "404" in err_str or "Connection refused" in err_str or "无法建立" in err_str:
            return {
                "status": "ERROR",
                "error_message": f"⚠️ ClickHouse 数据库未启动或不可达。请检查服务状态。原始错误: {err_str[:200]}",
                "sql_logic": sql,
                "is_infra_error": True
            }
        return {
            "status": "ERROR",
            "error_message": err_str,
            "sql_logic": sql
        }

# ──────────────────────────────────────────────────────────
# 暴露给 Agent 的工具集 (Decorated Tools)
# ──────────────────────────────────────────────────────────

@tool
async def execute_audit_sql(sql: str, db_type: str = "clickhouse") -> Any:
    """执行医疗相关 SQL 查询。"""
    return await _execute_audit_sql_logic(sql, db_type)

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
async def audit_medical_rule(rule_id: str) -> Dict[str, Any]:
    """
    [V59.4] 执行预定义的物理违规规则匹配。
    自动映射语义到物理算子，并异步执行。
    """
    logger.info(f"🔨 [TOOL] 执行物理违规规则引擎: {rule_id}")
    
    # 语义路由映射
    target_rule = ""
    rule_key = rule_id.upper()
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
        return {"report": f"未找到匹配的审计算子: {rule_id}", "evidence_count": 0, "raw_evidence": []}

    try:
        # 核心异步执行 (V72.0 注入业务容差)
        tolerance = 50000 if "REPEAT_BILLING" in target_rule else 1000
        raw_data = await _execute_audit_sql_logic(sql, return_raw=True, tolerance=tolerance)
        
        if isinstance(raw_data, str) and "失败" in raw_data:
             return {"report": f"物理引擎执行受阻: {raw_data}", "evidence_count": 0, "raw_evidence": []}
             
        count = len(raw_data)
        report_text = rule_engine.format_violation_report(target_rule, raw_data)
        
        return {
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "trace_hint": f"[规则引擎] 触发算子 {target_rule}，物理库命中 {count} 条违规证据"
        }
    except Exception as e:
        logger.error(f"规则引擎执行异常: {e}")
        return {
            "report": "物理探测异常", 
            "evidence_count": 0, 
            "error": str(e), 
            "raw_evidence": [], 
            "trace_hint": f"[规则引擎] {rule_id} 执行异常"
        }

@tool
async def run_anomaly_detection(algorithm_id: str) -> Dict[str, Any]:
    """
    [V59.4] 运行统计学异常检测算法。
    自动映射语义到物理算子，并异步执行。
    """
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
    [V110.0] 业务深度增强：语义扩展医疗编码 (ICD-10/ICD-9/三大目录)。
    当任务涉及特定疾病类别（如“妇科”、“肿瘤”）时，调用此工具获取精确的物理编码范围。
    """
    # [V110.1] 知识库映射 (Mock 级，实际应对接专业 ICD 向量库)
    MEDICAL_CODE_KB = {
        "妇科": {
            "icd10": ["O00", "O99"],
            "icd9": ["54.51", "65.0", "71.9"],
            "desc": "涉及妊娠、分娩和产褥期疾病及相关手术"
        },
        "肿瘤": {
            "icd10": ["C00", "D48"],
            "desc": "涉及恶性肿瘤、原位癌及性质未定肿瘤"
        },
        "眼科": {
            "icd10": ["H00", "H59"],
            "icd9": ["08.0", "16.9"],
            "desc": "涉及眼和附器疾病及相关手术"
        },
        "牙科": {
            "icd10": ["K00", "K14"],
            "icd9": ["23.0", "24.9"],
            "desc": "涉及口腔、涎腺和颌骨疾病"
        },
        "心内科": {
            "icd10": ["I00", "I99"],
            "icd9": ["35.0", "39.9"],
            "desc": "涉及循环系统疾病及心脏介入手术"
        }
    }
    
    q = intent.strip()
    matched = []
    for k, v in MEDICAL_CODE_KB.items():
        if k in q or q in k:
            res = f"【{k}】专业编码映射建议：\n"
            if "icd10" in v:
                res += f"- ICD-10 (疾病): {v['icd10'][0]} 至 {v['icd10'][1]} (建议 SQL: dise_no LIKE '{v['icd10'][0][0]}%')\n"
            if "icd9" in v:
                res += f"- ICD-9-CM3 (手术): {', '.join(v['icd9'])} (建议 SQL: oper_no IN {tuple(v['icd9'])})\n"
            res += f"- 业务说明: {v['desc']}"
            matched.append(res)
    
    if not matched:
        return f"当前标准编码库中未找到与 '{intent}' 直接相关的专业分类。建议：请直接尝试 LIKE '%{intent}%' 进行初步检索。"
    
    return "\n\n".join(matched)

