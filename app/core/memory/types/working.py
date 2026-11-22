"""
app/core/memory/types/working.py
================================
[Matt Pocock Deep Module] 二级工作记忆管理引擎 (Working Memory Engine)

核心职责：
1. L0 本地进程高速缓存：纳秒级读写响应，提供瞬时会话状态持有；
2. L1 Redis 分布式集群同步：保障多 Worker 与跨进程状态一致性，支持故障透明降级；
3. 穿透式召回与反向预热：L0 未命中或过期时穿透至 L1 并自动回填本地 L0；
4. 词法模糊检索与有效性感知过滤。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger

from app.core.memory.base import MemoryItem


class WorkingMemory:
    """二级工业级工作记忆深模块"""

    def __init__(
        self,
        redis_client: Any = None,
        key_prefix: str = "hsa:working:",
    ):
        self._redis = redis_client
        self._prefix = key_prefix
        self.cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _scoped_key(key: str, tenant_id: str = "default") -> str:
        """为非默认租户生成隔离键，默认租户保持原键以兼容既有行为"""
        tid = tenant_id or "default"
        return key if tid == "default" else f"{tid}:{key}"

    def store(self, key: str, value: Any, ttl: int = 3600, tenant_id: str = "default") -> None:
        """
        工业级二级工作记忆存储
        L0: 本地进程内存 (极速响应)
        L1: Redis 分布式集群 (跨进程一致性)
        """
        tid = tenant_id or "default"
        scoped_key = self._scoped_key(key, tid)

        # 1. 物理写入 Redis (核心分布式同步层)
        try:
            underlying = getattr(self._redis, "client", self._redis)
            if underlying:
                full_key = f"{self._prefix}{scoped_key}"
                serialized_val = json.dumps(value, ensure_ascii=False)
                underlying.setex(full_key, ttl, serialized_val)
        except Exception as e:
            logger.warning(f"⚠️ [WorkingMemory] Redis 同步失败，降级使用本地存储: {e}")

        # 2. 同步更新本地 L0 缓存
        self.cache[scoped_key] = {
            "val": value,
            "expire": datetime.now().timestamp() + ttl,
            "tenant_id": tid,
        }

    def recall(self, key: str, tenant_id: str = "default") -> Optional[Any]:
        """
        分布式工作记忆召回
        执行 L0 -> L1 穿透检索与反向预热
        """
        now_ts = datetime.now().timestamp()
        tid = tenant_id or "default"
        scoped_key = self._scoped_key(key, tid)

        # 路径 A: 命中本地有效 L0
        item = self.cache.get(scoped_key)
        if item and item.get("expire", 0) > now_ts:
            return item["val"]

        # 路径 B: 穿透至 Redis L1
        try:
            underlying = getattr(self._redis, "client", self._redis)
            if underlying:
                full_key = f"{self._prefix}{scoped_key}"
                data = underlying.get(full_key)
                if data:
                    val = json.loads(data)
                    # 反向补回本地 L0 提高后续命中率
                    self.cache[scoped_key] = {
                        "val": val,
                        "expire": now_ts + 3600,
                        "tenant_id": tid,
                    }
                    return val
        except Exception as e:
            logger.error(f"❌ [WorkingMemory] 跨进程记忆召回崩溃: {e}")

        return None

    def search(self, query: str, limit: int = 5, tenant_id: str = "default") -> List[MemoryItem]:
        """工作记忆混合检索：基于词法匹配的高性能召回（带租户隔离）"""
        results: List[MemoryItem] = []
        query_lower = (query or "").lower()
        now_ts = datetime.now().timestamp()
        tid = tenant_id or "default"

        for key, item in list(self.cache.items()):
            if item.get("expire", 0) < now_ts:
                continue
            if item.get("tenant_id", "default") != tid:
                continue

            content_str = str(item.get("val", "")).lower()
            if query_lower in content_str:
                expire_ts = item.get("expire", now_ts + 3600)
                raw_key = key[len(tid) + 1:] if tid != "default" and key.startswith(f"{tid}:") else key
                results.append(
                    MemoryItem(
                        content=item["val"],
                        memory_type="working",
                        importance=0.6,
                        metadata={"key": raw_key, "tenant_id": tid, "source": "working_cache_l0"},
                        timestamp=datetime.fromtimestamp(expire_ts - 3600),
                    )
                )
                if len(results) >= limit:
                    break

        return results

    def clear_expired(self) -> int:
        """清理已过期的本地 L0 条目"""
        now_ts = datetime.now().timestamp()
        expired_keys = [k for k, v in self.cache.items() if v.get("expire", 0) < now_ts]
        for k in expired_keys:
            self.cache.pop(k, None)
        return len(expired_keys)
