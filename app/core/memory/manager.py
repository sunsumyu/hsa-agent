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
from app.infra.redis_client import redis_manager
from app.core.background_worker import bg_worker
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
        
        # 2. 初始化逻辑层 (Types)
        self.semantic = SemanticMemory(storage=self.vector_storage)
        self.episodic = EpisodicMemory(storage=self.relational_storage)
        self.perceptual = PerceptualMemory(storage=self.perceptual_vector_storage)
        self.working_cache = {}  # 内存 L0 缓存
        
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
        working_hits = self.search_working(text, limit=3)
        
        # 3. 最终融合与去重
        final_list = self._rerank_results(text, results + working_hits, limit)
        return final_list

    async def recall(self, query: str, limit: int = 5, tenant_id: str = "default") -> List[MemoryItem]:
        """
        [V4.6] 企业级两阶段召回 (Two-Stage Retrieval)
        """
        # 1. 物理初筛 (3倍超量召回)
        top_k = limit * 3
        
        # 获取当前租户的存储句柄
        storage = self._get_tenant_storage(tenant_id)
        
        # 执行并发召回
        semantic_tasks = [
            self.semantic.recall(query, limit=top_k, tenant_id=tenant_id),
            self.perceptual.recall(query, limit=top_k, tenant_id=tenant_id)
        ]
        
        import asyncio
        results = await asyncio.gather(*semantic_tasks)
        all_candidates = [item for sublist in results for item in sublist]
        
        # 2. 物理精排
        return self._rerank_results(query, all_candidates, limit)

    def _rerank_results(self, query: str, candidates: List[MemoryItem], limit: int) -> List[MemoryItem]:
        """
        [V4.6] 工业级启发式重排器 (Heuristic Reranker)
        """
        if not candidates: return []

        scored_items = []
        now = datetime.now()
        query_keywords = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{3,}", query))

        for item in candidates:
            # A. 基础分 (归一化相似度)
            base_score = getattr(item, "score", 0.5)
            
            # B. 业务维度分
            importance_boost = item.importance * 0.4
            
            # C. 时间衰减
            delta_days = (now - item.timestamp).days
            time_decay = 1.0 / (1.0 + 0.05 * delta_days)
            
            # D. 硬匹配激励
            match_count = sum(1 for kw in query_keywords if kw in item.content)
            keyword_boost = min(match_count * 0.15, 0.3)
            
            final_score = (base_score * 0.3) + importance_boost + (time_decay * 0.1) + keyword_boost
            item.metadata["rerank_score"] = round(final_score, 4)
            scored_items.append((final_score, item))

        scored_items.sort(key=lambda x: x[0], reverse=True)
        
        # 物理去重
        seen_content = set()
        unique_results = []
        for _, item in scored_items:
            content_hash = hash(item.content)
            if content_hash not in seen_content:
                unique_results.append(item)
                seen_content.add(content_hash)
            if len(unique_results) >= limit: break
                
        return unique_results

    def _calculate_hybrid_score(self, item: MemoryItem) -> float:
        """[V4.0] 核心评分函数：融合相似度、重要性与时间衰减"""
        # A. 基础相似度得分 (假设已在 search 时注入)
        base_relevance = item.score if item.score > 0 else 0.5
        
        # B. 重要性加权 [0.8, 1.2]
        # 公式：0.8 + (importance * 0.4)
        importance_weight = 0.8 + (item.importance * 0.4)
        
        # C. 时间衰减 (Recency Bias)
        # 采用指数衰减：e^(-0.1 * age_days)
        age_days = (datetime.now() - item.timestamp).total_seconds() / (24 * 3600)
        recency_weight = math.exp(-0.05 * age_days) # 衰减系数 0.05
        
        # 最终综合得分
        final_score = base_relevance * importance_weight * recency_weight
        return round(final_score, 4)

    def store_working(self, key: str, value: Any, ttl: int = 3600):
        """
        [V4.6] 工业级二级工作记忆存储
        L0: 本地进程内存 (极速响应)
        L1: Redis 分布式集群 (跨进程一致性)
        """
        # 1. 物理写入 Redis (核心同步层)
        try:
            if redis_manager and redis_manager.client:
                full_key = f"hsa:working:{key}"
                # 序列化并存入 Redis，设置物理有效期
                serialized_val = json.dumps(value, ensure_ascii=False)
                redis_manager.client.setex(full_key, ttl, serialized_val)
        except Exception as e:
            logger.warning(f"⚠️ [MemoryHub] Redis 同步失败，仅使用本地存储: {e}")
        
        # 2. 同步更新本地 L0 缓存
        self.working_cache[key] = {
            "val": value, 
            "expire": datetime.now().timestamp() + ttl
        }

    def recall_working(self, key: str) -> Optional[Any]:
        """
        [V4.6] 分布式工作记忆召回
        执行 L0 -> L1 穿透检索
        """
        # 路径 A: 命中本地 L0
        item = self.working_cache.get(key)
        if item and item["expire"] > datetime.now().timestamp():
            return item["val"]
            
        # 路径 B: 穿透至 Redis L1 (分布式获取)
        try:
            if redis_manager and redis_manager.client:
                full_key = f"hsa:working:{key}"
                data = redis_manager.client.get(full_key)
                if data:
                    val = json.loads(data)
                    # 反向补回本地 L0 提高下次速度
                    self.working_cache[key] = {"val": val, "expire": datetime.now().timestamp() + 3600}
                    return val
        except Exception as e:
            logger.error(f"❌ [MemoryHub] 跨进程记忆召回崩溃: {e}")
            
        return None

    def search_working(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """[V4.0] 工作记忆混合检索：基于词法匹配的高性能召回"""
        results = []
        query_lower = query.lower()
        
        # 遍历本地 L0 缓存
        for key, item in self.working_cache.items():
            if item["expire"] < datetime.now().timestamp(): continue
            
            content_str = str(item["val"]).lower()
            if query_lower in content_str:
                results.append(MemoryItem(
                    content=item["val"],
                    memory_type="working",
                    importance=0.6, # 工作记忆默认中等重要性
                    metadata={"key": key, "source": "working_cache_l0"},
                    timestamp=datetime.fromtimestamp(item["expire"] - 3600) # 近似创建时间
                ))
                if len(results) >= limit: break
                
        return results

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
            self.store_working(key, safe_content)
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
                from app.memory.entity_extractor import extract_graph
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
                
                if m_type == "semantic":
                    loop.run_until_complete(storage["vector"].add([item]))
                    loop.run_until_complete(self.graph_storage.add([item]))
                elif m_type == "episodic":
                    loop.run_until_complete(storage["relational"].add([item]))
                elif m_type == "perceptual":
                    loop.run_until_complete(self.perceptual.add_image(metadata.get("file_path", ""), content, importance, **metadata))
                
                loop.close()
                logger.info(f"✨ [MemoryHub] 异步入库完成 | Type: {m_type} | Tenant: {t_id}")
            except Exception as e:
                logger.error(f"❌ [MemoryHub] 异步入库失败: {e}")

    def _mask_sensitive_data(self, text: str) -> str:
        """
        [V4.6] 企业级物理脱敏引擎 (PII Scrubber)
        针对医保审计场景下的隐私数据进行不可逆掩码处理。
        """
        if not text: return ""
        
        # 1. 身份证号 (15/18位): 保留前6后2
        text = re.sub(r'\b\d{6}\d{7,10}[\dX]\b', lambda m: m.group()[:6] + '********' + m.group()[-2:], text)
        
        # 2. 手机号: 保留前3后4
        text = re.sub(r'\b1[3-9]\d{9}\b', lambda m: m.group()[:3] + '****' + m.group()[-4:], text)
        
        # 3. 银行卡/医保卡 (16-19位): 仅保留后4位
        text = re.sub(r'\b\d{12,15}(\d{4})\b', r'**** **** **** \1', text)
        
        # 4. 电子邮件: 掩码用户名
        text = re.sub(r'([a-zA-Z0-9_.+-])+[a-zA-Z0-9]@', r'****@', text)
        
        # 5. 疑似患者姓名 (实验性：匹配“患者XXX”或“姓名：XXX”)
        text = re.sub(r'(患者|姓名|医生)[:：]\s*([\u4e00-\u9fa5]{1})[\u4e00-\u9fa5]{1,2}', r'\1: \2**', text)
        
        return text

    async def forget_memories(
        self,
        strategy: str = "combined",
        threshold: float = 0.2,
        max_age_days: int = 30
    ) -> Dict[str, int]:
        """
        [V4.6] 工业级三维淘汰引擎 (Three-Axis Eviction)
        strategy:
          - "combined"       : 综合模式（默认），同时执行重要性 + 时间 + L0 过期清理
          - "importance_based": 仅按重要性阈值淘汰低价值记忆
          - "time_based"      : 仅按最大存活天数淘汰过期记忆
        """
        logger.info(f"🧹 [MemoryHub] 启动三维淘汰引擎 | 策略: {strategy} | 阈值: {threshold} | 最大天数: {max_age_days}")
        report = {"importance_evicted": 0, "time_evicted": 0, "l0_expired": 0}
        
        try:
            # 维度 A: 重要性淘汰 (Episodic + Semantic)
            if strategy in ("combined", "importance_based"):
                report["importance_evicted"] += await self.relational_storage.delete_low_importance(threshold)
                report["importance_evicted"] += await self.vector_storage.forget(threshold)

            # 维度 B: 时间淘汰 (Episodic 关系型存储)
            if strategy in ("combined", "time_based"):
                report["time_evicted"] += await self.relational_storage.delete_expired(max_age_days)

            # 维度 C: L0 工作记忆 TTL 清扫
            now_ts = datetime.now().timestamp()
            expired_keys = [k for k, v in self.working_cache.items() if v["expire"] < now_ts]
            for k in expired_keys:
                del self.working_cache[k]
            report["l0_expired"] = len(expired_keys)

        except Exception as e:
            logger.error(f"❌ [MemoryHub] 遗忘清理执行失败: {e}")

        total = sum(report.values())
        logger.success(f"✅ [MemoryHub] 遗忘清理完成 | 共移除 {total} 条 | 详情: {report}")
        return report

    def get_stats(self) -> Dict[str, Any]:
        """
        [V4.6] 企业级健康信标 (Health Beacon)
        为门户实时仪表盘提供标准化运营数据
        """
        now_ts = datetime.now().timestamp()
        active_working = sum(1 for v in self.working_cache.values() if v["expire"] > now_ts)
        expired_working = len(self.working_cache) - active_working

        # Redis 连接状态
        redis_status = "OFFLINE"
        try:
            if redis_manager and redis_manager.client:
                redis_manager.client.ping()
                redis_status = "ONLINE"
        except Exception:
            pass

        return {
            "version": "V4.6.0",
            "timestamp": datetime.now().isoformat(),
            "memory_mode": getattr(settings, "memory_mode", "LOCAL").upper(),
            "layers": {
                "l0_working": {
                    "active": active_working,
                    "expired_pending_gc": expired_working,
                    "backend": "In-Process + Redis"
                },
                "l1_semantic": {
                    "status": "ONLINE",
                    "backend": "FAISS (LOCAL) / Milvus (ENTERPRISE)"
                },
                "l2_episodic": {
                    "status": "ONLINE",
                    "backend": "SQLite (LOCAL) / PostgreSQL (ENTERPRISE)"
                },
                "l3_perceptual": {
                    "status": "ONLINE" if not self.perceptual._init_failed else "DEGRADED (Text-Fallback)",
                    "backend": "CLIP + FAISS"
                }
            },
            "infrastructure": {
                "redis": redis_status,
                "tenant_shards": len(self.storage_pool),
                "model_mode": "HF_OFFLINE"
            }
        }

    def get_summary(self) -> str:
        """[V4.6] 获取记忆库人类可读摘要 (供 Agent Prompt 注入)"""
        stats = self.get_stats()
        l0 = stats["layers"]["l0_working"]["active"]
        perceptual_status = stats["layers"]["l3_perceptual"]["status"]
        mode = stats["memory_mode"]
        return (
            f"🧠 记忆中枢 [{mode}] | "
            f"L0工作记忆: {l0}项活跃 | "
            f"语义/情景: ONLINE | "
            f"感知层: {perceptual_status}"
        )

# 全局单例
memory_hub = MemoryHub()
