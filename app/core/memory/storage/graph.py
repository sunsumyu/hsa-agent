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
        图谱写入：通常涉及 Cypher 实体创建逻辑。
        目前版本主要用于查询，写入逻辑可后续根据业务扩展。
        """
        logger.warning("⚠️ [GraphStorage] 当前版本暂不支持异步批量写入，请使用 Neo4jManager 直接导入数据。")
        pass

    async def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """
        图谱检索：执行 Cypher 查询并转化为 MemoryItem。
        """
        if not self.manager.is_connected:
            logger.info("📡 [GraphStorage] Neo4j 未连接，正在尝试从本地 SQLite 图谱备份检索...")
            return self._search_local(query, limit)
            
        # 这里的 query 可以是 Cypher 或 关键字（通过 manager 路由）
        try:
            # 模拟从图谱提取关联 Schema 的逻辑
            # 在实际业务中，这里会根据 query 查找 Node/Relationship
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
