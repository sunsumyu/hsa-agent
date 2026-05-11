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
            result = await asyncio.to_thread(client.query, safe_sql)
            
            if return_raw:
                cols = result.column_names
                records = [{cols[j]: row[j] for j in range(len(cols))} for row in result.result_rows]
                return _sanitize_results(records, tolerance=tolerance)
            return f"查询成功，返回 {len(result.result_rows)} 条记录。"
            
        return "MySQL 暂不支持在此路径执行。"
    except Exception as e:
        logger.error(f"[SQL_EXEC_ERROR] {e}")
        return {
            "status": "ERROR",
            "error_message": str(e),
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
    """列出可用审计数据表。"""
    return "fqz_gz_jzsj_all_ql (就诊结算全量表)"

@tool
def get_table_schema(table_name: str) -> str:
    """获取 ClickHouse 物理表的真实字段结构，返回字段名和类型列表。"""
    try:
        client = get_clickhouse_client()
        result = client.query(f"DESCRIBE TABLE {table_name}")
        fields = [f"{row[0]} ({row[1]})" for row in result.result_rows]
        return "\n".join(fields)
    except Exception as e:
        return f"获取表结构失败: {e}"

@tool
def calculator(expr: str) -> str:
    """高精度数学计算器。"""
    try: return str(eval(expr, {"__builtins__": None}, {}))
    except: return "计算失败"

# ──────────────────────────────────────────────────────────
# 规则引擎与专家知识 (M3 成果落地)
# ──────────────────────────────────────────────────────────

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医保审计专家知识库。"""
    # 模拟专家经验：对于重复住院，需要关注同一天不同机构的结算重叠
    return "专家提示：同一患者同一天在不同医疗机构存在重叠住院时间，通常涉及违规套取基金。建议核查 start_date 和 end_date 的交集。"

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
