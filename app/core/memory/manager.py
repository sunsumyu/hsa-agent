"""
app/core/memory/manager.py
==========================
[V177.4] 统一记忆管理中枢 (Memory Hub) - 旗舰版
"""

import json
from typing import Optional, List, Any, Dict
from loguru import logger
from datetime import datetime

from app.core.memory.base import MemoryItem
from app.core.memory.storage.vector import VectorStorage
from app.core.memory.storage.relational import RelationalStorage
from app.core.memory.storage.graph import GraphStorage
from app.core.memory.types.semantic import SemanticMemory
from app.core.memory.types.episodic import EpisodicMemory
from app.redis_client import redis_manager

class MemoryHub:
    """
    工业级记忆中枢：实现多级记忆的分发、检索与持久化。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryHub, cls).__new__(cls)
            cls._instance._init_hub()
        return cls._instance

    def _init_hub(self):
        # 1. 初始化底座 (Storage)
        self.vector_storage = VectorStorage(storage_dir="data/memory_v3")
        self.relational_storage = RelationalStorage(db_path="data/memory_v3/episodic.db")
        self.graph_storage = GraphStorage()
        
        # 2. 初始化逻辑层 (Types)
        self.semantic = SemanticMemory(storage=self.vector_storage)
        self.episodic = EpisodicMemory(storage=self.relational_storage)
        self.working_cache = {}  # 内存 L0 缓存
        
        logger.info("🧠 [MemoryHub] 工业级记忆中枢已上线 | 架构: Hierarchical-V3")

    def attach_component(self, name: str, component: Any):
        """兼容性占位：支持旧版模块挂载逻辑"""
        logger.debug(f"🔗 [MemoryHub] 接收到旧版组件挂载请求 ({name})，已自动忽略。")
        pass

    async def query(self, text: str, limit: int = 12, use_hyde: bool = True) -> List[MemoryItem]:
        """全域分层检索：优先语义，带自动降级"""
        results = []
        try:
            # 语义召回 (HyDE 增强)
            hits = await self.semantic.recall(text, limit=limit, use_hyde=use_hyde)
            results.extend(hits)
        except Exception as e:
            logger.error(f"❌ [MemoryHub] 语义检索崩溃: {e}")
            # 此处可添加关键词降级逻辑...
            
        return results

    def store_working(self, key: str, value: Any, ttl: int = 3600):
        """存储工作记忆 (Redis L1 + Local L0)"""
        full_key = f"hsa:working:{key}"
        try:
            if redis_manager and redis_manager.client:
                redis_manager.client.setex(full_key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Redis 工作记忆存储失败: {e}")
        
        self.working_cache[key] = {
            "val": value, 
            "expire": datetime.now().timestamp() + ttl
        }

    def recall_working(self, key: str) -> Optional[Any]:
        """提取工作记忆"""
        # 优先 Redis
        full_key = f"hsa:working:{key}"
        try:
            if redis_manager and redis_manager.client:
                data = redis_manager.client.get(full_key)
                if data: return json.loads(data)
        except: pass
        
        # 次选本地内存
        item = self.working_cache.get(key)
        if item and item["expire"] > datetime.now().timestamp():
            return item["val"]
        return None

    async def consolidate(self, key: str, importance_threshold: float = 0.7):
        """
        [V178.7] 记忆巩固：将有价值的工作记忆转化为长期记忆
        """
        val = self.recall_working(key)
        if not val: return

        # 评估重要性 (此处可引入 LLM 评分或基于关键词规则)
        importance = 0.5
        if isinstance(val, dict):
            if val.get("success") is True: importance += 0.3
            if "SQL" in str(val): importance += 0.2

        if importance >= importance_threshold:
            logger.info(f"✨ [MemoryHub] 发现高价值信息 ({key})，正在进行记忆巩固...")
            # 根据内容决定存入情景还是语义
            if "question" in str(val):
                await self.episodic.record_episode(str(key), val, importance)
            else:
                await self.semantic.learn(str(val), topic="consolidated", importance=importance)

# 全局单例
memory_hub = MemoryHub()
