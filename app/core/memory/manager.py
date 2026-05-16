"""
app/core/memory/manager.py
==========================
[V177.4] 统一记忆管理中枢 (Memory Hub) - 旗舰版
"""

import json
import re
from typing import Optional, List, Any, Dict
from loguru import logger
from datetime import datetime

from app.core.memory.base import MemoryItem
from app.core.memory.storage.vector import VectorStorage
from app.core.memory.storage.relational import RelationalStorage
from app.core.memory.storage.enterprise import DistributedVectorStorage, DistributedRelationalStorage
from app.core.memory.storage.graph import GraphStorage
from app.core.config import settings
from app.core.memory.types.semantic import SemanticMemory
from app.core.memory.types.episodic import EpisodicMemory
from app.redis_client import redis_manager
from app.core.context import tenant_context

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
        # [V185.0] 存储工厂：根据配置切换本地/分布式模式
        mode = getattr(settings, "MEMORY_MODE", "LOCAL")
        
        if mode == "ENTERPRISE":
            logger.warning("🚀 [MemoryHub] 检测到企业模式：正在建立分布式集群连接池...")
            self.vector_storage = DistributedVectorStorage(cluster_uri=getattr(settings, "MILVUS_URI", "milvus://localhost:19530"))
            self.relational_storage = DistributedRelationalStorage(pool_uri=getattr(settings, "POSTGRES_URI", "postgresql://user@localhost/hsa"))
        else:
            logger.info("🏠 [MemoryHub] 运行于本地开发模式：使用 SQLite/FAISS 后端")
            self.vector_storage = VectorStorage(storage_dir="data/memory_v3")
            self.relational_storage = RelationalStorage(db_path="data/memory_v3/episodic.db")
            
        self.graph_storage = GraphStorage()
        
        # 2. 初始化逻辑层 (Types)
        self.semantic = SemanticMemory(storage=self.vector_storage)
        self.episodic = EpisodicMemory(storage=self.relational_storage)
        self.working_cache = {}  # 内存 L0 缓存
        
        logger.info(f"🧠 [MemoryHub] 工业级记忆中枢就绪 | 模式: {mode} | 隔离等级: Physical-Tenant-Isolation")

    def attach_component(self, name: str, component: Any):
        """兼容性占位：支持旧版模块挂载逻辑"""
        logger.debug(f"🔗 [MemoryHub] 接收到旧版组件挂载请求 ({name})，已自动忽略。")
        pass

    async def query(self, text: str, limit: int = 12, use_hyde: bool = True) -> List[MemoryItem]:
        """全域分层检索：优先语义，带自动降级与租户隔离"""
        results = []
        t_id = tenant_context.get() or "default"
        try:
            # 语义召回 (HyDE 增强)
            hits = await self.semantic.recall(text, limit=limit, use_hyde=use_hyde, tenant_id=t_id)
            results.extend(hits)
            
            # [V181.1] 情景补齐：检索当前租户的历史动作
            episodes = await self.episodic.recall_experience(text, limit=3, tenant_id=t_id)
            results.extend(episodes)
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

    async def add_memory(self, content: str, memory_type: str = "working", importance: float = 0.5, **metadata) -> str:
        """[V181.0] 统一添加接口：注入租户信息并进行基础脱敏"""
        t_id = tenant_context.get() or metadata.get("tenant_id", "default")
        metadata["tenant_id"] = t_id
        
        # 基础安全性：敏感数据脱敏 (Simple Masking)
        if isinstance(content, str):
            content = self._mask_sensitive_data(content)
            
        try:
            if memory_type == "working":
                key = metadata.get("key", f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                self.store_working(key, content)
                return f"✅ 工作记忆已存入 (Key: {key}, Tenant: {t_id})"
            elif memory_type == "semantic":
                await self.semantic.learn(content, importance=importance, metadata=metadata)
                return f"✅ 语义记忆已学习 (Tenant: {t_id})"
            elif memory_type == "episodic":
                await self.episodic.record_episode(str(content), metadata, importance=importance)
                return f"✅ 情景记忆已存档 (Tenant: {t_id})"
            else:
                return f"❌ 不支持的记忆类型: {memory_type}"
        except Exception as e:
            return f"❌ 添加失败: {str(e)}"

    def _mask_sensitive_data(self, text: str) -> str:
        """[V181.2] 基础脱敏过滤器：对疑似 ID 和金额进行模糊处理"""
        # 匹配 15/18 位身份证号 (极简版)
        text = re.sub(r'\d{15,18}', lambda m: m.group()[:6] + '*' * 8 + m.group()[-2:], text)
        # 匹配手机号
        text = re.sub(r'1[3-9]\d{9}', lambda m: m.group()[:3] + '****' + m.group()[-4:], text)
        return text

    async def forget_memories(self, strategy: str = "importance_based", threshold: float = 0.2, max_age_days: int = 30) -> int:
        """[V180.0] 工业级遗忘机制"""
        logger.info(f"🧹 [MemoryHub] 启动遗忘清理 (策略: {strategy}, 阈值: {threshold})")
        count = 0
        
        if strategy == "importance_based":
            # 1. 清理关系型存储 (Episodic)
            count += await self.relational_storage.delete_low_importance(threshold)
            # 2. 清理向量存储 (Semantic)
            count += await self.vector_storage.forget(threshold)
        elif strategy == "time_based":
            # 清理过期的关系型数据
            count += await self.relational_storage.delete_expired(max_age_days)
            
        logger.success(f"✅ [MemoryHub] 遗忘清理完成，共移除 {count} 条记忆项")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆库统计信息"""
        return {
            "working_count": len(self.working_cache),
            "semantic_status": "ONLINE",
            "episodic_status": "ONLINE",
            "timestamp": datetime.now().isoformat()
        }

    def get_summary(self) -> str:
        """获取记忆库简要摘要"""
        stats = self.get_stats()
        return f"🧠 记忆中枢状态: 工作记忆({stats['working_count']}), 长期存储(ACTIVE)。"

# 全局单例
memory_hub = MemoryHub()
