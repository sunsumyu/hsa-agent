"""
[V59.6] Neo4j 连接管理：懒加载 + 阻塞优化
"""
import os
from loguru import logger
from typing import Optional

class Neo4jManager:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        self.is_connected = False
        # [V59.6] 移除 __init__ 中的阻塞式连接，改为懒加载

    def _ensure_connected(self):
        """仅在真正需要时尝试连接，并设置极短超时"""
        if self.is_connected and self.driver:
            return

        try:
            from neo4j import GraphDatabase
            # 设置连接超时为 3 秒，避免卡死
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password),
                connection_timeout=3.0,
                max_connection_lifetime=600
            )
            # verify_connectivity 是阻塞的，控制在极短时间内
            self.driver.verify_connectivity()
            self.is_connected = True
            logger.info(f"✅ Neo4j 物理连接成功: {self.uri}")
        except Exception as e:
            self.is_connected = False
            error_msg = f"❌ [NEO4J FATAL] 物理连接失败: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def get_driver(self):
        self._ensure_connected()
        return self.driver

# 单例
neo4j_manager = Neo4jManager()
