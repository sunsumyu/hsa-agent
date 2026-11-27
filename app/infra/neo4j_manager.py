"""
app/infra/neo4j_manager.py
==========================
[V59.3 Phase 3-B / Matt Pocock Deep Module / Facade] Neo4j 图数据库连接池与查询管理门面
聚焦于真实 Neo4j 数据库连接、拓扑查询、Cypher 物理执行与本体结构发现。

底层解耦委托至专职深模块：
- neo4j_protocol_healer (物理端口探测与协议自愈)
- neo4j_ontology_provider (医保审计图谱本体结构与权威提示语)
- field_knowledge_graph (字段别名映射与医学语义意图图谱，保持向后兼容重导出)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from loguru import logger

# ── 向后兼容重导出字段知识图谱深模块 ──────────────────────────────
from app.infra.field_knowledge_graph import (
    FieldKnowledgeGraph,
    expand_medical_intent,
    MEDICAL_KNOWLEDGE_MAP,
    FIELD_ALIAS_REGISTRY,
)
from app.infra.neo4j_protocol_healer import neo4j_protocol_healer, Neo4jProtocolHealer
from app.infra.neo4j_ontology_provider import neo4j_ontology_provider, Neo4jOntologyProvider

load_dotenv()


class Neo4jManager:
    """
    Neo4j 物理图数据库连接与会话管理器。
    支持连接快速探活、协议自愈 (neo4j:// -> bolt://) 与延迟加载。
    """

    def __init__(
        self,
        protocol_healer: Optional[Neo4jProtocolHealer] = None,
        ontology_provider: Optional[Neo4jOntologyProvider] = None,
    ):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        if not self.password:
            logger.warning("[SECURITY] NEO4J_PASSWORD 未设置，Neo4j 连接将失败。请在 .env 中配置。")
        self.driver = None
        self.is_connected = False
        # [V131.0] 防重试标志：连接失败后不再重复尝试和打印日志
        self._connection_attempted = False
        self._protocol_healer = protocol_healer or neo4j_protocol_healer
        self._ontology_provider = ontology_provider or neo4j_ontology_provider

    def _init_connection(self):
        """初始化物理图数据库连接，执行前置探活与协议自愈"""
        try:
            from neo4j import GraphDatabase

            # 1. 物理协议自愈：针对本地/WSL 环境，bolt:// 比 neo4j:// 更具鲁棒性
            connection_uri = self._protocol_healer.heal_uri(self.uri)

            # 2. 物理端口探测：避免在网络不通时产生长阻塞或 defunct connection
            reachable, host, port = self._protocol_healer.probe_port(connection_uri, timeout=2.0)
            if not reachable:
                self._connection_attempted = True
                return

            self.driver = GraphDatabase.driver(
                connection_uri,
                auth=(self.user, self.password),
                connection_timeout=15.0,  # 降低超时时间，快速失败
            )
            self.driver.verify_connectivity()
            self.is_connected = True
            logger.info(f">>> 成功直连至 Neo4j 图数据库 ({connection_uri.split('://')[0]} 模式)。")
        except Exception as e:
            err_msg = str(e)
            if "routing information" in err_msg.lower() and "bolt://" not in self.uri:
                logger.error("❌ [NEO4J ROUTING ERROR] 路由发现失败。请检查 .env，建议将 NEO4J_URI 的协议头改为 bolt://")
            else:
                logger.error(f"❌ [NEO4J ERROR] 真实图数据库连接失败: {e}。")
            self.driver = None
            self.is_connected = False
            self._connection_attempted = True

    def get_driver(self):
        """获取底层 Neo4j Driver，未连接时抛出结构化运行时异常"""
        if not self.driver and not self._connection_attempted:
            self._init_connection()
        if not self.is_connected:
            raise RuntimeError(
                "Neo4j 服务未连接，无法执行图查询。请检查 .env 中的 NEO4J_URI（建议使用 bolt://）和 Neo4j 服务状态。"
            )
        return self.driver

    def execute_cypher(self, cypher: str, params: Optional[Dict[str, Any]] = None):
        """[V4.0] 物理执行 Cypher 语句，支持事务包装"""
        if not self.driver:
            self.get_driver()
        try:
            with self.driver.session() as session:
                return session.run(cypher, params or {})
        except Exception as e:
            logger.error(f"Cypher 执行失败: {e} | Query: {cypher}")
            raise e

    def get_ontology(self) -> str:
        """获取图数据库的本体结构（标签和关系类型）"""
        if not self.driver:
            self._init_connection()
        if not self.is_connected:
            # 自愈防守：连接未就绪时，优先返回静态权威本体说明
            return self.get_audit_graph_hints()

        try:
            with self.driver.session() as session:
                labels_res = session.run("CALL db.labels()")
                labels = [record["label"] for record in labels_res]

                rel_types_res = session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] for record in rel_types_res]

                return self._ontology_provider.format_ontology(labels, rel_types)
        except Exception as e:
            logger.error(f"获取 Neo4j 本体失败: {e}")
            return self.get_audit_graph_hints()

    def get_audit_graph_hints(self) -> str:
        """[企业级] 返回图谱业务模式提示（委托至 Neo4jOntologyProvider）"""
        return self._ontology_provider.get_audit_graph_hints()


# ── 模块级代理与单例 ───────────────────────────────────────────
from app.core.container import LazyProxy

neo4j_manager = LazyProxy("neo4j_manager")
field_kg = LazyProxy("field_kg")
