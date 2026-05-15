"""
app/core/memory/storage/graph.py
================================
[V178.6] 图存储后端 (Neo4j Graph Storage)
"""

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
            return []
            
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

    def get_hints(self) -> str:
        """获取图谱操作提示词"""
        return self.manager.get_audit_graph_hints()
