"""
app/core/memory/health_inspector.py
===================================
[Matt Pocock Deep Module] 记忆中枢健康巡检与运营度量信标

核心职责：
1. 聚合巡检 L0/L1/L2/L3 各级记忆层次的实时状态与待回收负载
2. 探活 Redis 与多租户物理分片集群的基础设施连通性
3. 规范化输出运营监控信标字典与 Agent Prompt 注入用摘要
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


class MemoryHealthInspector:
    """记忆中枢健康巡检器深模块"""

    def inspect(
        self,
        working_cache: Dict[str, Any],
        perceptual_component: Any,
        storage_pool: Dict[str, Any],
        memory_mode: str = "LOCAL",
        redis_client: Optional[Any] = None,
        vector_storage: Optional[Any] = None,
        relational_storage: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """巡检并收集全域记忆存储健康度量指标"""
        now_ts = datetime.now().timestamp()
        active_working = sum(
            1 for v in working_cache.values()
            if isinstance(v, dict) and v.get("expire", 0) > now_ts
        )
        expired_working = len(working_cache) - active_working

        # Redis 连接状态探活
        redis_status = "OFFLINE"
        if redis_client is not None:
            try:
                # 兼容直接传入 redis_manager 或 redis.Redis 客户端
                client = getattr(redis_client, "client", redis_client)
                if client is not None and hasattr(client, "ping"):
                    client.ping()
                    redis_status = "ONLINE"
            except Exception:
                redis_status = "OFFLINE"

        # 感知层状态探测
        perceptual_status = "ONLINE"
        if perceptual_component is not None:
            if getattr(perceptual_component, "_init_failed", False):
                perceptual_status = "DEGRADED (Text-Fallback)"
        else:
            perceptual_status = "NOT_ATTACHED"

        # 语义层 & 情景层运行期度量采集
        sem_stats = self._safe_storage_stats(vector_storage)
        epi_stats = self._safe_storage_stats(relational_storage)

        return {
            "version": "V4.6.0",
            "timestamp": datetime.now().isoformat(),
            "memory_mode": (memory_mode or "LOCAL").upper(),
            "layers": {
                "l0_working": {
                    "active": active_working,
                    "expired_pending_gc": expired_working,
                    "backend": "In-Process + Redis",
                },
                "l1_semantic": {
                    "status": "ONLINE",
                    "backend": "FAISS (LOCAL) / Milvus (ENTERPRISE)",
                    **sem_stats,
                },
                "l2_episodic": {
                    "status": "ONLINE",
                    "backend": "SQLite (LOCAL) / PostgreSQL (ENTERPRISE)",
                    **epi_stats,
                },
                "l3_perceptual": {
                    "status": perceptual_status,
                    "backend": "CLIP + FAISS",
                },
            },
            "infrastructure": {
                "redis": redis_status,
                "tenant_shards": len(storage_pool) if isinstance(storage_pool, dict) else 0,
                "model_mode": "HF_OFFLINE",
            },
        }

    @staticmethod
    def _safe_storage_stats(storage: Optional[Any]) -> Dict[str, Any]:
        """安全采集存储后端的条数与命中率度量"""
        if storage is None or not hasattr(storage, "get_stats"):
            return {}
        try:
            st = storage.get_stats()
            total = int(getattr(st, "total_items", 0) or 0)
            hits = int(getattr(st, "hits", 0) or 0)
            misses = int(getattr(st, "misses", 0) or 0)
            size_bytes = int(getattr(st, "storage_size_bytes", 0) or 0)
            total_queries = hits + misses
            hit_rate = round(hits / total_queries, 4) if total_queries > 0 else 0.0
            return {
                "total_items": total,
                "hits": hits,
                "misses": misses,
                "hit_rate": hit_rate,
                "storage_size_bytes": size_bytes,
            }
        except Exception:
            return {}

    def format_summary(self, stats: Dict[str, Any]) -> str:
        """根据健康信标指标生成人类可读的 Prompt 注入紧凑摘要"""
        layers = stats.get("layers", {})
        l0 = layers.get("l0_working", {}).get("active", 0)
        l1 = layers.get("l1_semantic", {})
        l2 = layers.get("l2_episodic", {})
        perceptual_status = layers.get("l3_perceptual", {}).get("status", "ONLINE")
        mode = stats.get("memory_mode", "LOCAL")

        sem_info = f"{l1['total_items']}条(命中率{l1.get('hit_rate', 0.0):.0%})" if "total_items" in l1 else "ONLINE"
        epi_info = f"{l2['total_items']}条" if "total_items" in l2 else "ONLINE"
        return (
            f"🧠 记忆中枢 [{mode}] | "
            f"L0工作记忆: {l0}项活跃 | "
            f"语义: {sem_info} | "
            f"情景: {epi_info} | "
            f"感知层: {perceptual_status}"
        )


# 单例默认实例
health_inspector = MemoryHealthInspector()
