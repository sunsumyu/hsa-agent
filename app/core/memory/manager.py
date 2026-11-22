"""
app/core/memory/manager.py
==========================
[V177.4] 统一记忆管理中枢 (Memory Hub) - 旗舰版
"""

import os
import json
import re
from typing import Optional, List, Any, Dict
from loguru import logger
from datetime import datetime
import math
import numpy as np

from app.core.memory.base import MemoryItem
from app.core.memory.storage.vector import VectorStorage
from app.core.memory.storage.relational import RelationalStorage
from app.core.memory.storage.enterprise import DistributedVectorStorage, DistributedRelationalStorage
from app.core.memory.storage.graph import GraphStorage
from app.core.config import settings
from app.core.memory.types.semantic import SemanticMemory
from app.core.memory.types.episodic import EpisodicMemory
from app.core.memory.types.perceptual import PerceptualMemory
from app.core.memory.types.working import WorkingMemory
from app.infra.redis_client import redis_manager
from app.core.background_worker import bg_worker
from app.core.context import tenant_context
from app.core.memory.eviction_engine import eviction_engine, MemoryEvictionEngine
from app.core.memory.health_inspector import health_inspector, MemoryHealthInspector
from app.core.memory.pii_scrubber import pii_scrubber, PIIScrubber
from app.core.memory.hybrid_reranker import hybrid_reranker, HybridReranker
from app.core.memory.conflict_arbiter import memory_conflict_arbiter

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
        # 优先读取 pydantic 字段，兼容旧版 getattr 逻辑
        mode = getattr(settings, "memory_mode", "LOCAL").upper()
        
        if mode == "ENTERPRISE":
            logger.warning("🚀 [MemoryHub] 检测到企业模式：正在建立分布式集群连接池...")
            milvus_uri = getattr(settings, "milvus_uri", getattr(settings, "MILVUS_URI", "milvus://localhost:19530"))
            postgres_uri = getattr(settings, "postgres_uri", getattr(settings, "POSTGRES_URI", "postgresql://user@localhost/hsa"))
            self.vector_storage = DistributedVectorStorage(cluster_uri=milvus_uri)
            self.relational_storage = DistributedRelationalStorage(pool_uri=postgres_uri)
        else:
            logger.info("🏠 [MemoryHub] 运行于本地开发模式：使用 SQLite/FAISS 后端")
            self.vector_storage = VectorStorage(storage_dir="data/memory_v3")
            self.relational_storage = RelationalStorage(db_path="data/memory_v3/episodic.db")
            
        # [V4.5] 物理隔离连接池
        self.storage_pool: Dict[str, Dict[str, Any]] = {}
        
        # [V4.0] 感知记忆独立存储
        self.perceptual_vector_storage = VectorStorage(storage_dir="data/memory_v4/perceptual")
        self.graph_storage = GraphStorage()
        
        # 2. 初始化逻辑层 (Types)
        self.semantic = SemanticMemory(storage=self.vector_storage)
        self.episodic = EpisodicMemory(storage=self.relational_storage)
        self.perceptual = PerceptualMemory(storage=self.perceptual_vector_storage)
        self.working = WorkingMemory(redis_client=redis_manager)
        self.working_cache = self.working.cache  # 内存 L0 缓存共享同一字典引用
        self.eviction_engine = eviction_engine
        self.health_inspector = health_inspector
        self._gc_timer = None
        self._gc_running = False
        
        logger.info(f"🧠 [MemoryHub] 工业级记忆中枢已加固 (V4.6.0) | 二阶段检索 | PII脱敏 | L0-L1分布式工作记忆")

    def attach_component(self, name: str, component: Any):
        """兼容性占位：支持旧版模块挂载逻辑"""
        logger.debug(f"🔗 [MemoryHub] 接收到旧版组件挂载请求 ({name})，已自动忽略。")
        pass

    async def query(self, text: str, limit: int = 12) -> List[MemoryItem]:
        """
        [V4.6] 全域混合检索 (Industrial Rank Fusion)
        集成语义、情景、感知及工作记忆，并执行二阶段物理重排。
        """
        t_id = tenant_context.get() or "default"
        logger.debug(f"🔍 [MemoryHub] 收到全局检索请求 | Tenant: {t_id} | Query: {text[:30]}")
        
        # 1. 执行全量召回
        results = await self.recall(text, limit=limit, tenant_id=t_id)
        
        # 2. 补全工作记忆 (L0)
        working_hits = self.search_working(text, limit=3, tenant_id=t_id)
        
        # 3. 最终融合与去重
        final_list = self._rerank_results(text, results + working_hits, limit)
        return final_list

    async def recall(self, query: str, limit: int = 5, tenant_id: str = "default") -> List[MemoryItem]:
        """
        [V4.6] 企业级两阶段召回 (Two-Stage Retrieval)
        并发检索语义、感知与情景记忆，并按租户物理分片路由。
        """
        # 1. 物理初筛 (3倍超量召回)
        top_k = limit * 3
        
        # 获取当前租户的存储句柄
        storage = self._get_tenant_storage(tenant_id)
        
        # 执行并发召回 (语义 + 感知 + 情景)
        recall_tasks = [
            self.semantic.recall(query, limit=top_k, tenant_id=tenant_id, storage=storage["vector"]),
            self.perceptual.recall(query, limit=top_k, tenant_id=tenant_id),
            self.episodic.recall_experience(query, limit=top_k, tenant_id=tenant_id, storage=storage["relational"]),
        ]
        
        import asyncio
        results = await asyncio.gather(*recall_tasks)
        all_candidates = [item for sublist in results for item in sublist]
        
        # 2. 物理精排
        return self._rerank_results(query, all_candidates, limit)

    def _rerank_results(self, query: str, candidates: List[MemoryItem], limit: int) -> List[MemoryItem]:
        """[V4.6 Deep Module] 工业级启发式重排器 (Heuristic Reranker)"""
        return hybrid_reranker.rerank(query=query, candidates=candidates, limit=limit)

    def _calculate_hybrid_score(self, item: MemoryItem) -> float:
        """[V4.0 Deep Module] 核心评分函数：融合相似度、重要性与时间衰减"""
        return hybrid_reranker.calculate_hybrid_score(item)

    def store_working(self, key: str, value: Any, ttl: int = 3600, tenant_id: Optional[str] = None):
        """[V4.6 Deep Module] 工业级二级工作记忆存储"""
        t_id = tenant_id or tenant_context.get() or "default"
        self.working.store(key, value, ttl=ttl, tenant_id=t_id)

    def recall_working(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """[V4.6 Deep Module] 分布式工作记忆召回"""
        t_id = tenant_id or tenant_context.get() or "default"
        return self.working.recall(key, tenant_id=t_id)

    def search_working(self, query: str, limit: int = 5, tenant_id: Optional[str] = None) -> List[MemoryItem]:
        """[V4.0 Deep Module] 工作记忆混合检索：基于词法匹配的高性能召回"""
        t_id = tenant_id or tenant_context.get() or "default"
        return self.working.search(query, limit=limit, tenant_id=t_id)

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

    def _get_tenant_storage(self, tenant_id: str) -> Dict[str, Any]:
        """
        [V4.6] 企业级存储路由网关
        1. ENTERPRISE 模式：直接返回具备分片能力的全局集群句柄
        2. LOCAL 模式：执行物理目录分片与句柄缓存
        """
        mode = getattr(settings, "memory_mode", "LOCAL").upper()
        
        # 路径 A: 集群模式 (分布式存储本身具备逻辑隔离能力)
        if mode == "ENTERPRISE":
            return {
                "vector": self.vector_storage,
                "relational": self.relational_storage
            }
            
        # 路径 B: 本地物理分片模式
        if tenant_id not in self.storage_pool:
            base_path = f"data/memory_v4/tenants/{tenant_id}"
            
            try:
                # 物理环境预检：确保父目录存在且具备写入权限
                os.makedirs(base_path, exist_ok=True)
                
                logger.info(f"📁 [MemoryHub] 正在为租户 {tenant_id} 初始化物理存储分片...")
                self.storage_pool[tenant_id] = {
                    "vector": VectorStorage(storage_dir=f"{base_path}/vector"),
                    "relational": RelationalStorage(db_path=f"{base_path}/episodic.db")
                }
            except Exception as e:
                logger.error(f"❌ [MemoryHub] 租户物理分片初始化失败: {e}")
                # 紧急降级：返回默认存储句柄防止流程中断
                return {
                    "vector": self.vector_storage,
                    "relational": self.relational_storage
                }
                
        return self.storage_pool[tenant_id]

    async def add_memory(self, content: str, memory_type: str = "working", importance: float = 0.5, **metadata) -> str:
        """[V4.5] 工业级记忆入库：支持异步流水线与物理脱敏"""
        t_id = tenant_context.get() or metadata.get("tenant_id", "default")
        metadata["tenant_id"] = t_id
        
        # 1. 物理脱敏 (PII Scrubbing)
        safe_content = self._mask_sensitive_data(str(content))
        
        # 2. 工作记忆同步处理
        if memory_type == "working":
            key = metadata.get("key", f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            self.store_working(key, safe_content, tenant_id=t_id)
            return f"✅ [Working] 已存入 L0 缓存 (Key: {key})"
            
        # 3. 长期记忆异步处理 (非阻塞主审计流程)
        bg_worker.submit(
            self._background_ingestion_pipeline,
            safe_content, memory_type, importance, metadata, t_id
        )
        
        return f"🚀 [MemoryHub] 记忆已提交至异步入库流水线 (Tenant: {t_id})"

    def _background_ingestion_pipeline(self, content: str, m_type: str, importance: float, metadata: Dict, t_id: str):
        """[物理硬化] 后台入库流水线：处理实体提取与分布式锁"""
        lock_key = f"memory:write:{t_id}"
        
        # 使用分布式锁确保物理文件写入不冲突
        with redis_manager.dist_lock(lock_key, timeout=20) as acquired:
            if not acquired:
                logger.warning(f"⚠️ [MemoryHub] 获取租户 {t_id} 写入锁失败，任务将重新入队。")
                return
                
            try:
                storage = self._get_tenant_storage(t_id)
                
                # 物理实体提取 (调用 LLM/NLP)
                from app.core.memory.entity_extractor import extract_graph
                graph_data = extract_graph([content])
                extracted_entities = []
                for node in graph_data.get("nodes", []):
                    cat_map = {0: "Hospital", 1: "Patient", 2: "Policy", 3: "Record", 4: "Amount"}
                    extracted_entities.append({
                        "label": cat_map.get(node.get("category"), "GenericEntity"),
                        "name": node.get("name")
                    })
                metadata["extracted_entities"] = extracted_entities
                
                # 物理持久化
                item = MemoryItem(content=content, importance=importance, metadata=metadata, timestamp=datetime.now())
                
                # 运行异步存储逻辑
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if m_type == "semantic":
                        if hasattr(storage["vector"], "upsert_with_conflict_resolution"):
                            loop.run_until_complete(
                                storage["vector"].upsert_with_conflict_resolution(item, arbiter=memory_conflict_arbiter)
                            )
                        else:
                            loop.run_until_complete(storage["vector"].add([item]))
                        if hasattr(self, "graph_storage") and self.graph_storage is not None:
                            loop.run_until_complete(self.graph_storage.add([item]))
                    elif m_type == "episodic":
                        loop.run_until_complete(storage["relational"].add([item]))
                    elif m_type == "perceptual":
                        loop.run_until_complete(self.perceptual.add_image(metadata.get("file_path", ""), content, importance, **metadata))
                finally:
                    loop.close()
                logger.info(f"✨ [MemoryHub] 异步入库完成 | Type: {m_type} | Tenant: {t_id}")
            except Exception as e:
                logger.error(f"❌ [MemoryHub] 异步入库失败: {e}")

    def _mask_sensitive_data(self, text: str) -> str:
        """[V4.6 Deep Module] 企业级物理脱敏引擎 (PII Scrubber)"""
        return pii_scrubber.mask_sensitive_data(text)

    async def forget_memories(
        self,
        strategy: str = "combined",
        threshold: float = 0.2,
        max_age_days: int = 30
    ) -> Dict[str, int]:
        """
        [V4.6 Deep Module] 工业级三维淘汰引擎
        委托至 MemoryEvictionEngine 深模块执行参数校验与三维协同清理。
        """
        return await self.eviction_engine.evict(
            relational_storage=self.relational_storage,
            vector_storage=self.vector_storage,
            working_cache=self.working_cache,
            strategy=strategy,
            threshold=threshold,
            max_age_days=max_age_days,
        )

    def start_periodic_gc(
        self,
        interval_seconds: int = 3600,
        strategy: str = "combined",
        threshold: float = 0.2,
        max_age_days: int = 30,
    ) -> None:
        """启动后台周期性三维记忆 GC 调度（守护线程定时器）"""
        import threading
        self.stop_periodic_gc()
        self._gc_running = True

        def _run_and_reschedule():
            if not self._gc_running:
                return
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self.forget_memories(strategy=strategy, threshold=threshold, max_age_days=max_age_days)
                )
            except Exception as e:
                logger.error(f"❌ [MemoryHub] 定时 GC 执行异常: {e}")
            finally:
                loop.close()

            if self._gc_running:
                self._gc_timer = threading.Timer(interval_seconds, _run_and_reschedule)
                self._gc_timer.daemon = True
                self._gc_timer.start()

        self._gc_timer = threading.Timer(interval_seconds, _run_and_reschedule)
        self._gc_timer.daemon = True
        self._gc_timer.start()
        logger.info(f"🕒 [MemoryHub] 已启动后台周期性记忆 GC | 间隔: {interval_seconds}s")

    def stop_periodic_gc(self) -> None:
        """停止后台周期性记忆 GC 调度"""
        self._gc_running = False
        if self._gc_timer is not None:
            self._gc_timer.cancel()
            self._gc_timer = None

    def get_stats(self) -> Dict[str, Any]:
        """
        [V4.6 Deep Module] 企业级健康信标
        委托至 MemoryHealthInspector 深模块聚合多层度量指标。
        """
        return self.health_inspector.inspect(
            working_cache=self.working_cache,
            perceptual_component=self.perceptual,
            storage_pool=self.storage_pool,
            memory_mode=getattr(settings, "memory_mode", "LOCAL"),
            redis_client=redis_manager,
            vector_storage=self.vector_storage,
            relational_storage=self.relational_storage,
        )

    def get_summary(self) -> str:
        """[V4.6 Deep Module] 获取记忆库人类可读摘要 (供 Agent Prompt 注入)"""
        stats = self.get_stats()
        return self.health_inspector.format_summary(stats)

# 全局单例
memory_hub = MemoryHub()
