"""
app/skills/federated_graph_executor.py
======================================
联邦图谱分析与跨库侧载执行引擎（Deep Module）

核心职责：
1. execute_fraud_ring_cypher: 执行图谱 Cypher 探测，具备空间隔离拦截、异步线程隔离、失败本体自适应建议能力。
2. execute_federated_sideloader: 执行 Neo4j -> ClickHouse 跨库联邦侧载，自动提取实体、生成内存临时表、安全批量写入并兜底所有异常契约。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, Callable, Dict, List, Optional
from loguru import logger

from app.skills.analysis_operator_resolver import (
    validate_cypher_spatial_isolation,
    extract_entity_ids,
)
from app.skills.federated_sideload_buffer import federated_sideload_buffer


async def execute_fraud_ring_cypher(
    cypher: str,
    neo4j_mgr: Any = None,
) -> Dict[str, Any]:
    """
    执行 Neo4j Cypher 图谱查询。
    自动应用空间隔离规则物理拦截越界关系表，并在发生错误时自适应提供当前本体结构反馈。
    """
    logger.info(f"🕸️ [GRAPH] 执行 Cypher 查询: {cypher}")

    # 1. 空间隔离验证：物理拦截关系表进入图查询
    isolation_err = validate_cypher_spatial_isolation(cypher)
    if isolation_err:
        logger.warning(f"🚨 [SPACE_ISOLATION] 拦截到越界图查询意图: {cypher}")
        return {
            "status": "ERROR",
            "error_message": isolation_err,
            "sql_logic": cypher,
        }

    # 2. 延迟加载 Neo4j 管理器
    if neo4j_mgr is None:
        from app.infra.neo4j_manager import neo4j_manager
        mgr = neo4j_manager
    else:
        mgr = neo4j_mgr

    try:
        def _exec_cypher():
            driver = mgr.get_driver()
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
            "trace_hint": f"[图谱分析] 执行 Cypher 命中 {count} 条深层关联线索",
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ [GRAPH ERROR] Neo4j 物理查询失败: {error_msg}")

        # 自动反馈：拉取本体结构告知 Agent，防止其继续臆造标签
        try:
            current_ontology = mgr.get_ontology()
        except Exception:
            current_ontology = ""

        return {
            "status": "ERROR",
            "error_message": f"图数据库查询失败: {error_msg}。",
            "suggested_ontology": current_ontology,
            "suggestion": (
                "检测到您可能使用了不存在的标签或属性。请参考上述 [Neo4j Graph Ontology] 重新编写 Cypher。"
                "重点：业务数据（患者等）可能尚未注入，如果 Ontology 为空，请先尝试 lookup_medical_schema。"
            ),
        }


async def execute_federated_sideloader(
    cypher: str,
    return_key: str = "",
    neo4j_mgr: Any = None,
    clickhouse_client_getter: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """
    [企业级联邦侧载执行引擎]
    执行 Cypher 图谱检索，并将发现的核心实体 ID 自动侧载到 ClickHouse 内存临时表。
    """
    logger.info(f"🕸️ [SIDELOADER] 开始联邦查询 (Neo4j -> ClickHouse)")

    # 1. 空间隔离验证
    isolation_err = validate_cypher_spatial_isolation(cypher)
    if isolation_err:
        logger.warning(f"🚨 [SPACE_ISOLATION] 侧载拦截到越界图查询意图: {cypher}")
        return {
            "status": "ERROR",
            "error_message": isolation_err,
            "sql_logic": cypher,
        }

    # 2. 延迟加载 Neo4j 管理器
    if neo4j_mgr is None:
        from app.infra.neo4j_manager import neo4j_manager
        mgr = neo4j_manager
    else:
        mgr = neo4j_mgr

    try:
        def _exec_cypher():
            driver = mgr.get_driver()
            with driver.session() as session:
                return [dict(record) for record in session.run(cypher)]

        records = await asyncio.to_thread(_exec_cypher)
        if not records:
            return {"status": "SUCCESS", "message": "图谱查询完成，未发现匹配团伙/节点。", "count": 0}

        ids = extract_entity_ids(records, return_key=return_key)
        if not ids:
            return {"status": "ERROR", "error_message": "无法从 Cypher 结果中提取有效的实体 ID 进行侧载。"}

        # 3. 获取 ClickHouse 客户端并通过 FederatedSideloadBuffer 安全侧载
        if clickhouse_client_getter is None:
            from app.infra.db_conn import get_clickhouse_client
            client = get_clickhouse_client()
        else:
            client = clickhouse_client_getter()

        success, temp_table, err = federated_sideload_buffer.sideload_ids_to_clickhouse(
            ids=ids,
            client=client,
        )
        if not success:
            return {"status": "ERROR", "error_message": f"侧载到 ClickHouse 失败: {err}"}

        return federated_sideload_buffer.format_sideload_response(temp_table=temp_table, count=len(ids))
    except Exception as e:
        logger.error(f"❌ [SIDELOADER ERROR] 联邦侧载失败: {e}")
        return {"status": "ERROR", "error_message": f"联邦侧载失败: {e}"}
