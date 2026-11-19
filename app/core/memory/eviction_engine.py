"""
app/core/memory/eviction_engine.py
==================================
[Matt Pocock Deep Module] 记忆中枢三维垃圾回收与遗忘淘汰引擎

核心职责：
1. 校验淘汰清理策略参数合法性（strategy, threshold, max_age_days）
2. 协同执行三维淘汰流水线：
   - 维度 A: 重要性淘汰 (Episodic 关系型存储 + Semantic 向量存储)
   - 维度 B: 时间存活淘汰 (Episodic 关系型过期清理)
   - 维度 C: L0 本地/进程内工作记忆 TTL 物理清扫
3. 异常弹性隔离：局部存储清理失败不崩溃全局流程
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger


class MemoryEvictionEngine:
    """工业级三维记忆遗忘与垃圾淘汰引擎深模块"""

    SUPPORTED_STRATEGIES = ("combined", "importance_based", "time_based")

    def validate_params(self, strategy: str, threshold: float, max_age_days: int) -> None:
        """校验遗忘淘汰输入参数的严格边界"""
        if strategy not in self.SUPPORTED_STRATEGIES:
            raise ValueError(
                f"不支持的遗忘淘汰策略: {strategy}，可选策略为: {', '.join(self.SUPPORTED_STRATEGIES)}"
            )
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"重要性阈值 threshold 必须在 [0.0, 1.0] 范围内，当前值: {threshold}")
        if max_age_days <= 0:
            raise ValueError(f"最大存活天数 max_age_days 必须大于等于 1，当前值: {max_age_days}")

    async def evict(
        self,
        relational_storage: Any,
        vector_storage: Any,
        working_cache: Dict[str, Any],
        strategy: str = "combined",
        threshold: float = 0.2,
        max_age_days: int = 30,
    ) -> Dict[str, int]:
        """执行三维记忆淘汰回收流程"""
        self.validate_params(strategy, threshold, max_age_days)

        logger.info(
            f"🧹 [EvictionEngine] 启动三维淘汰 | 策略: {strategy} | 阈值: {threshold} | 最大天数: {max_age_days}"
        )
        report = {"importance_evicted": 0, "time_evicted": 0, "l0_expired": 0}

        try:
            # 维度 A: 重要性淘汰 (Episodic + Semantic)
            if strategy in ("combined", "importance_based"):
                if relational_storage and hasattr(relational_storage, "delete_low_importance"):
                    try:
                        res = await relational_storage.delete_low_importance(threshold)
                        report["importance_evicted"] += int(res or 0)
                    except Exception as e:
                        logger.error(f"[EvictionEngine] 关系存储重要性淘汰失败: {e}")

                if vector_storage and hasattr(vector_storage, "forget"):
                    try:
                        res = await vector_storage.forget(threshold)
                        report["importance_evicted"] += int(res or 0)
                    except Exception as e:
                        logger.error(f"[EvictionEngine] 向量存储重要性淘汰失败: {e}")

            # 维度 B: 时间淘汰 (Episodic 关系型存储)
            if strategy in ("combined", "time_based"):
                if relational_storage and hasattr(relational_storage, "delete_expired"):
                    try:
                        res = await relational_storage.delete_expired(max_age_days)
                        report["time_evicted"] += int(res or 0)
                    except Exception as e:
                        logger.error(f"[EvictionEngine] 关系存储过期淘汰失败: {e}")

            # 维度 C: L0 工作记忆 TTL 清扫
            if isinstance(working_cache, dict):
                now_ts = datetime.now().timestamp()
                expired_keys = [
                    k for k, v in working_cache.items()
                    if isinstance(v, dict) and v.get("expire", 0) < now_ts
                ]
                for k in expired_keys:
                    working_cache.pop(k, None)
                report["l0_expired"] = len(expired_keys)

        except Exception as e:
            logger.error(f"❌ [EvictionEngine] 遗忘清理执行失败: {e}")

        total = sum(report.values())
        logger.success(f"✅ [EvictionEngine] 遗忘清理完成 | 共移除 {total} 条 | 详情: {report}")
        return report


# 单例默认实例
eviction_engine = MemoryEvictionEngine()
