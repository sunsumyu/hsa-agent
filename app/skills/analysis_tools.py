"""
app/skills/analysis_tools.py
============================
[Phase 3.2] Rule engine, anomaly detection, and graph analysis tools.

Extracted from tools.py. These @tool functions run pre-defined violation
rules, statistical anomaly algorithms, and Neo4j Cypher graph queries.
"""

import re
import json
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from langchain_core.tools import tool

from app.skills.audit_rules import rule_engine
from app.skills.anomaly_algorithms import anomaly_detector
from app.infra.db_conn import get_clickhouse_client
from app.skills.sql_tools import _execute_audit_sql_logic


@tool
async def audit_medical_rule(rule_id: str, extra_filters: Optional[Dict[str, str]] = None) -> str:
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
    elif "CONTACT_SHARING" in rule_key or "联系方式" in rule_key: target_rule = "CONTACT_SHARING"
    else: target_rule = rule_key
    
    sql = rule_engine.get_rule_sql(target_rule, extra_filters=extra_filters)
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
            "sql_logic": sql, # [NEW]
            "trace_hint": f"[规则引擎] 触发算子 {target_rule}，物理库命中 {count} 条违规证据"
        })
    except Exception as e:
        logger.error(f"规则引擎执行异常: {e}")
        return json.dumps({
            "report": "物理探测异常", 
            "evidence_count": 0, 
            "error": str(e), 
            "raw_evidence": [], 
            "sql_logic": sql, # [NEW]
            "trace_hint": f"[规则引擎] {rule_id} 执行异常"
        })

@tool
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
        return json.dumps({"report": f"未找到匹配的算法算子: {algorithm_id}", "evidence_count": 0, "raw_evidence": []})

    try:
        # V72.0 注入业务容差 (统计异常通常具有较高基数)
        raw_data = await _execute_audit_sql_logic(sql, return_raw=True, tolerance=20000)
        
        if isinstance(raw_data, str) and "失败" in raw_data:
             return json.dumps({"report": f"物理算法执行受阻: {raw_data}", "evidence_count": 0, "raw_evidence": []})
             
        count = len(raw_data)
        report_text = anomaly_detector.format_anomaly_report(target_algo, raw_data)
        
        return json.dumps({
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "sql_logic": sql, # [NEW]
            "trace_hint": f"[异常算法] 触发算子 {target_algo}，物理库命中 {count} 条异常线索"
        })
    except Exception as e:
        logger.error(f"算法引擎执行异常: {e}")
        return json.dumps({
            "report": "物理探测异常", 
            "evidence_count": 0, 
            "error": str(e), 
            "raw_evidence": [], 
            "sql_logic": sql, # [NEW]
            "trace_hint": f"[异常算法] {algorithm_id} 执行异常"
        })

# ──────────────────────────────────────────────────────────
# 知识检索增强 (RAG) V4.6 落地
# ──────────────────────────────────────────────────────────

@tool
async def ingest_knowledge_document(file_path: str, importance: float = 0.9) -> str:
    """
    [V4.6] 将外部文档（PDF/Excel/Markdown）物理索引至审计知识库。
    Agent 在发现新的政策文件或审计指南时应调用此工具。
    """
    from app.core.rag.tool import rag_tool
    res = await rag_tool.add_document(file_path, importance=importance)
    return json.dumps(res, ensure_ascii=False)

@tool
async def query_knowledge_base(query: str, limit: int = 5, expert_mode: bool = False) -> str:
    """
    [V4.6] 检索医保审计政策、法律法规与专家指南。
    - 普通模式: 快速语义匹配。
    - 专家模式 (expert_mode=True): 启用 MQE 查询扩展与 HyDE 假设文档技术，适用于疑难审计点、政策边界模糊等场景，能大幅提升召回精度。
    """
    from app.core.rag.tool import rag_tool
    if expert_mode:
        return await rag_tool.search_knowledge_expanded(query, limit=limit, enable_mqe=True, enable_hyde=True)

# ──────────────────────────────────────────────────────────
# Neo4j 团伙欺诈分析工具 (Graph Analysis)
# ──────────────────────────────────────────────────────────

@tool
async def query_fraud_ring(cypher: str) -> Dict[str, Any]:
    """
    [V59.6] 执行 Neo4j Cypher 查询，用于发现隐蔽的医疗欺诈团伙。
    【⚠️ 物理隔离警告】：此工具仅能对 Neo4j 图数据库执行 Cypher 查询。图数据库中只包含 Patient, Hospital, Phone 等图节点，
    绝对不包含 fqz_gz_jzsj_all_ql 等关系型物理数据表！严禁在 Cypher 查询中引用任何 fqz_ 开头的表，也严禁将此查询嵌套在 SQL 中！
    如需结合业务明细查询，请优先使用 federated_graph_sideloader 工具进行跨库侧载。
    """
    from app.infra.neo4j_manager import neo4j_manager
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
async def federated_graph_sideloader(cypher: str, return_key: str = "") -> Dict[str, Any]:
    """
    [企业级联邦侧载工具] 
    执行 Cypher 图谱检索，并将发现的核心实体 ID 自动侧载到 ClickHouse 内存临时表。
    【⚠️ 跨库分阶段强制规范】：Neo4j (Cypher) 与 ClickHouse (SQL) 是物理隔离的，绝对无法在单个 SQL 语句中直接嵌套执行 Cypher 语法！
    你必须分两步执行：
    1. 首先调用此工具（传入纯 Cypher 语句，严禁包含 fqz_ 开头的关系表），它会返回一个 ClickHouse 临时表名（例如 fqz_temp_sl_xxxx）。
    2. 在后续步骤中，编写标准 SQL 语句，使用 `INNER JOIN fqz_temp_sl_xxxx ON 主表.关键ID = fqz_temp_sl_xxxx.id` 关联查询结算明细。
    """
    from app.infra.neo4j_manager import neo4j_manager
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
