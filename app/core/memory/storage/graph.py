"""
app/core/memory/storage/graph.py
================================
[V178.6] 图存储后端 (Neo4j Graph Storage)
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.memory.base import MemoryItem, BaseStorage
from app.neo4j_manager import neo4j_manager

class GraphStorage(BaseStorage):
    """
    图存储驱动：封装 Neo4j 的物理操作，支持知识图谱与实体关联。
    """
    def __init__(self):
        self.manager = neo4j_manager
        self.local_db_path = "data/memory_v3/local_graph_data.db"

    async def add(self, items: List[MemoryItem]):
        """
        [V4.0] 图谱主动写入：将记忆内容中的实体与关系固化至 Neo4j。
        """
        if not self.manager.is_connected: return
        
        for item in items:
            # 提取元数据中的实体信息 (由 MemoryHub 注入)
            entities = item.metadata.get("extracted_entities", [])
            for ent in entities:
                label = ent.get("label", "GenericEntity")
                name = ent.get("name", "Unknown")
                
                # 简单 MERGE 逻辑：保证节点唯一性并建立与记忆项的联系
                cypher = f"MERGE (e:{label} {{name: $name}}) " \
                         f"MERGE (m:MemoryItem {{id: $mid}}) " \
                         f"MERGE (m)-[:MENTIONS]->(e) " \
                         f"SET m.content = $content, m.timestamp = $ts"
                
                params = {
                    "name": name,
                    "mid": item.metadata.get("id", str(hash(str(item.content)))),
                    "content": str(item.content)[:200],
                    "ts": item.timestamp.isoformat()
                }
                try:
                    self.manager.execute_cypher(cypher, params)
                except: pass # 忽略写入失败，保证主流程不中断

    async def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """
        图谱检索：执行 Cypher 查询并转化为 MemoryItem。
        """
        if not self.manager.is_connected:
            logger.info("📡 [GraphStorage] Neo4j 未连接，正在尝试从本地 SQLite 图谱备份检索...")
            return self._search_local(query, limit)
            
        # 这里的 query 可以是 Cypher 或 关键字（通过 manager 路由）
        try:
            # 物理路径：通过 Neo4j 本体提取语义关联 Schema
            ontology = self.manager.get_ontology()
            item = MemoryItem(
                content=ontology,
                memory_type="semantic",
                metadata={"source": "neo4j_graph"}
            )
            return [item]
        except Exception as e:
            logger.error(f"图存储检索失败: {e}")
            return []

    def _search_local(self, query: str, limit: int) -> List[MemoryItem]:
        """从本地 SQLite 备份中进行关键词匹配检索"""
        try:
            import os
            if not os.path.exists(self.local_db_path):
                return []
                
            with sqlite3.connect(self.local_db_path) as conn:
                cursor = conn.execute(
                    "SELECT labels, properties FROM nodes WHERE properties LIKE ? LIMIT ?",
                    (f"%{query}%", limit)
                )
                rows = cursor.fetchall()
                
                results = []
                for labels, props in rows:
                    content = f"Node({labels}): {props}"
                    results.append(MemoryItem(
                        content=content,
                        memory_type="semantic",
                        metadata={"source": "local_graph_backup"}
                    ))
                return results
        except Exception as e:
            logger.error(f"本地图谱检索失败: {e}")
            return []

    def get_hints(self) -> str:
        """获取图谱操作提示词"""
        return self.manager.get_audit_graph_hints()
