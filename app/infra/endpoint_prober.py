"""
app/infra/endpoint_prober.py
============================
[V201.0 / Matt Pocock Deep Module] 算力端点主动探活与自愈拨测门面深模块
对熔断/冷却状态的物理节点定期发送低成本探活请求 (max_tokens=1)，
并在节点恢复后自动重置状态机，同步持久化至 Redis。
"""

import os
import asyncio
from typing import Any
from loguru import logger

from app.infra.usage_tracker import usage_tracker
from app.infra.endpoint_pool_manager import endpoint_pool_manager
from app.infra.redis_client import redis_manager
from app.infra.endpoint_ping_probe import EndpointPingProbe
from app.infra.endpoint_healing_coordinator import EndpointHealingCoordinator


class EndpointProber:
    """端点主动探活与自愈拨测器门面"""

    def __init__(self, factory: Any = None):
        self.factory = factory
        self._pinger = EndpointPingProbe(factory=factory)
        self._healer = EndpointHealingCoordinator()

    async def probe_all_endpoints(self) -> None:
        """主动探活所有可用与处于熔断/冷却中的节点，实现智能探测自愈"""
        logger.info("🔍 [HealthCheck] 开始单次全量节点健康拨测...")

        endpoints_to_probe = {}
        for pool_id, pool in endpoint_pool_manager.pools.items():
            for ep in pool.endpoints:
                endpoints_to_probe[ep.id] = (ep, pool_id)

        healthy_count = 0
        recovered_count = 0
        failed_count = 0

        for ep_id, (ep, _) in endpoints_to_probe.items():
            needs_probe = self._healer.is_node_cooling_or_blacklisted(
                ep_id,
                pool_manager=endpoint_pool_manager,
                tracker=usage_tracker,
            )

            if needs_probe:
                logger.info(f"⏳ [HealthCheck] 发现处于熔断或冷却的节点: {ep_id}，启动主动探活拨测...")
                success = await self._probe_single_endpoint(ep_id, ep)
                if success:
                    self._healer.heal_node(
                        ep_id,
                        pool_manager=endpoint_pool_manager,
                        tracker=usage_tracker,
                    )
                    recovered_count += 1
                else:
                    logger.warning(f"❌ [HealthCheck] 节点 {ep_id} 拨测依然失败，继续维持封禁。")
                    failed_count += 1
            else:
                healthy_count += 1

            # 同步状态至 Redis
            self._healer.sync_node_health_to_redis(
                ep_id,
                pool_manager=endpoint_pool_manager,
                tracker=usage_tracker,
                redis_client=redis_manager,
            )

        logger.info(f"📊 [HealthCheck] 拨测完成: 正常={healthy_count} | 恢复={recovered_count} | 封禁中={failed_count}")

    async def _probe_single_endpoint(self, ep_id: str, ep: Any) -> bool:
        """对单个物理节点发送最廉价的 ping 请求以验证可用性 (委托至 EndpointPingProbe)"""
        # 若 factory 动态变更，同步至 pinger
        if self._pinger.factory != self.factory:
            self._pinger.factory = self.factory
        return await self._pinger.ping_endpoint(ep_id, ep)

    async def run_health_check(self) -> None:
        """周期性健康检查循环"""
        interval_seconds = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "300"))
        logger.info(f"[HealthCheck] 启动, interval={interval_seconds}s")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.probe_all_endpoints()
            except asyncio.CancelledError:
                logger.info("[HealthCheck] 收到取消信号, 优雅退出")
                break
            except Exception as e:
                logger.warning(f"[HealthCheck] 巡检异常: {e}")
