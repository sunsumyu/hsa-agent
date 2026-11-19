"""
Model Pool Router Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates pool endpoint selection,
adaptive fallback chains (with_fallbacks), and role-based asynchronous routing.
"""
import time
from typing import Optional, Dict, Any, Tuple
from loguru import logger


class ModelPoolRouter:
    """算力池智能寻址与角色路由深模块"""

    def __init__(self, pool_manager: Any = None, usage_tracker: Any = None, llm_factory: Any = None):
        self._pool_manager = pool_manager
        self._usage_tracker = usage_tracker
        self._llm_factory = llm_factory

    @property
    def pool_manager(self):
        if self._pool_manager is None:
            from app.infra.endpoint_pool_manager import endpoint_pool_manager
            self._pool_manager = endpoint_pool_manager
        return self._pool_manager

    @property
    def usage_tracker(self):
        if self._usage_tracker is None:
            from app.infra.usage_tracker import usage_tracker
            self._usage_tracker = usage_tracker
        return self._usage_tracker

    @property
    def llm_factory(self):
        if self._llm_factory is None:
            from app.infra.llm_factory import LLMFactory
            self._llm_factory = LLMFactory()
        return self._llm_factory

    def get_llm_from_pool(self, pool_id: str) -> Tuple[Any, str]:
        """从指定算力池中挑选最优端点与备用降级链"""
        selected_ep = self.pool_manager.select_best_endpoint(pool_id)
        if not selected_ep:
            raise ValueError(f"!!! [算力枯竭] 池 {pool_id} 及其降级链已全部失效。")

        main_llm = self.llm_factory.create_llm(selected_ep.id, selected_ep)
        pool = self.pool_manager.pools.get(pool_id)
        fallback_objects = []
        if pool:
            for ep in pool.endpoints:
                if ep.id != selected_ep.id:
                    is_safe, _, _, _ = self.usage_tracker.check_limit(ep.id)
                    if is_safe:
                        f_llm = self.llm_factory.create_llm(ep.id, ep)
                        if f_llm:
                            fallback_objects.append(f_llm)

        if main_llm is None:
            if fallback_objects:
                main_llm = fallback_objects.pop(0)
            else:
                raise ValueError(f"!!! [算力枯竭] 节点 {selected_ep.id} 及备选节点均未能成功创建 LLM。")

        if fallback_objects:
            return main_llm.with_fallbacks(fallback_objects), selected_ep.id
        return main_llm, selected_ep.id

    def get_adaptive_llm(self, model_id: Optional[str] = None, require_tools: bool = True) -> Tuple[Any, str]:
        """获取自适应降级 LLM 实例"""
        if model_id:
            for pool in self.pool_manager.pools.values():
                for ep in pool.endpoints:
                    if ep.id == model_id or ep.model_name == model_id:
                        return self.llm_factory.create_llm(ep.id, ep), ep.id
        pool_id = "tier-1-chat" if require_tools else "tier-2-chat"
        return self.get_llm_from_pool(pool_id)

    async def get_llm_by_role(
        self,
        role: str,
        retry_count: int = 0,
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, str]:
        """异步高可用角色路由与冷却换绑递归重试"""
        model_override = None
        if config and isinstance(config, dict):
            model_override = config.get("configurable", {}).get("model_override")

        # 1. 初始寻址
        if model_override:
            llm, m_id = self.get_adaptive_llm(model_id=model_override)
        else:
            role_cfg = self.pool_manager.roles.get(role)
            if role_cfg and hasattr(role_cfg, "preferred_endpoint") and role_cfg.preferred_endpoint and retry_count == 0:
                logger.info(f"📍 [Role-Binding] 角色 {role} 优先绑定端点: {role_cfg.preferred_endpoint}")
                llm, m_id = self.get_adaptive_llm(model_id=role_cfg.preferred_endpoint)
            else:
                pool_id = role_cfg.pool if role_cfg else "tier-1-chat"
                llm, m_id = self.get_llm_from_pool(pool_id)

        # 2. 快速冷却状态过滤
        if retry_count > 5:
            raise ValueError(f"All nodes for role {role} are banned.")

        state = self.pool_manager.states.get(m_id)
        if state and state.is_cooling and time.time() < state.cooldown_until:
            logger.warning(f"[FastCheck] Node {m_id} still in cooldown, switching.")
            return await self.get_llm_by_role(role, retry_count + 1, config)

        logger.debug(f"[FastCheck] Node {m_id} is ready.")
        return llm, m_id
