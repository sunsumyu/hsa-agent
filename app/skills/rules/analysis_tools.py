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

from app.skills.analysis_operator_runner import (
    execute_rule_operator,
    execute_anomaly_operator,
)


@tool
async def audit_medical_rule(rule_id: str, extra_filters: Optional[Dict[str, str]] = None) -> str:
    """[V176.0] 加固版规则引擎
    执行预定义的物理违规规则匹配。自动映射语义到物理算子，并异步执行。
    """
    return await execute_rule_operator(rule_id=rule_id, extra_filters=extra_filters)


@tool
async def run_anomaly_detection(algorithm_id: str, threshold: float = 0.95) -> str:
    """[V176.0] 加固版异常检测
    运行统计学异常检测算法。自动映射语义到物理算子，并异步执行。
    """
    return await execute_anomaly_operator(algorithm_id=algorithm_id, threshold=threshold)


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
    return await rag_tool.search_knowledge(query, limit=limit)

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
    from app.skills.federated_graph_executor import execute_fraud_ring_cypher
    return await execute_fraud_ring_cypher(cypher)

@tool
def expand_medical_codes(intent: str) -> str:
    """
    [V125.0] 业务深度增强：从知识库检索医疗编码建议 (ICD-10/ICD-9)。
    """
    from app.skills.expert_knowledge_retriever import resolve_medical_code_mapping
    return resolve_medical_code_mapping(intent)

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
    from app.skills.federated_graph_executor import execute_federated_sideloader
    return await execute_federated_sideloader(cypher, return_key=return_key)

