"""
Endpoint Healing Coordinator Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates node cooling state
interrogation, recovery state machine updates, and Redis health synchronization
behind clear static and instance methods.
"""
from typing import Any, Optional
from loguru import logger


class EndpointHealingCoordinator:
    """端点故障自愈与健康状态同步协调器"""

    @staticmethod
    def is_node_cooling_or_blacklisted(
        ep_id: str,
        pool_manager: Any = None,
        tracker: Any = None,
    ) -> bool:
        """检查节点是否处于冷却状态或熔断黑名单中"""
        if pool_manager is None:
            from app.infra.endpoint_pool_manager import endpoint_pool_manager
            pool_manager = endpoint_pool_manager
        if tracker is None:
            from app.infra.usage_tracker import usage_tracker
            tracker = usage_tracker

        state = pool_manager.states.get(ep_id)
        is_cooling = bool(state and state.is_cooling)
        is_blacklisted = ep_id in tracker.blacklist_expiry
        return is_cooling or is_blacklisted

    @staticmethod
    def heal_node(
        ep_id: str,
        pool_manager: Any = None,
        tracker: Any = None,
    ) -> None:
        """恢复节点算力链路：重置冷却状态与熔断黑名单"""
        if pool_manager is None:
            from app.infra.endpoint_pool_manager import endpoint_pool_manager
            pool_manager = endpoint_pool_manager
        if tracker is None:
            from app.infra.usage_tracker import usage_tracker
            tracker = usage_tracker

        pool_manager.record_success(ep_id)
        tracker.record_success(ep_id)
        logger.success(f"💖 [HealthCheck] 节点 {ep_id} 拨测成功！立即激活恢复算力链路。")

    @staticmethod
    def sync_node_health_to_redis(
        ep_id: str,
        pool_manager: Any = None,
        tracker: Any = None,
        redis_client: Any = None,
    ) -> None:
        """同步节点健康状态至持久化存储 Redis"""
        if pool_manager is None:
            from app.infra.endpoint_pool_manager import endpoint_pool_manager
            pool_manager = endpoint_pool_manager
        if tracker is None:
            from app.infra.usage_tracker import usage_tracker
            tracker = usage_tracker
        if redis_client is None:
            from app.infra.redis_client import redis_manager
            redis_client = redis_manager

        state = pool_manager.states.get(ep_id)
        is_active = True
        if ep_id in tracker.blacklist_expiry:
            is_active = False
        elif state and state.is_cooling:
            is_active = False

        redis_client.record_node_health(ep_id, is_active)
