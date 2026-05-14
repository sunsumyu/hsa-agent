import os
import json
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
from pydantic import BaseModel
from app.schemas import EndpointConfig, PoolConfig, RoleConfigV2, UsageStats
from app.usage_tracker import usage_tracker

class EndpointState:
    """接入点实时状态追踪"""
    def __init__(self, cfg: EndpointConfig):
        self.config = cfg
        self.id = cfg.id
        self.stability = usage_tracker.get_stability_score(cfg.id)
        self.is_cooling = False
        self.cooldown_until = 0.0

    def refresh_stability(self):
        self.stability = usage_tracker.get_stability_score(self.id)

class EndpointPoolManager:
    def __init__(self, pool_config_path="configs/endpoint_pools.json", 
                       role_config_path="configs/role_configs.json"):
        self.pool_config_path = pool_config_path
        self.role_config_path = role_config_path
        self.pools: Dict[str, PoolConfig] = {}
        self.roles: Dict[str, RoleConfigV2] = {}
        self.states: Dict[str, EndpointState] = {}
        self._load_all_configs()

    def _load_all_configs(self):
        """加载池化配置并初始化状态"""
        try:
            # 1. 加载池配置
            if os.path.exists(self.pool_config_path):
                with open(self.pool_config_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    for p_id, p_cfg in data.get("pools", {}).items():
                        pool = PoolConfig(**p_cfg)
                        self.pools[p_id] = pool
                        # 初始化接入点状态
                        for ep in pool.endpoints:
                            if ep.id not in self.states:
                                self.states[ep.id] = EndpointState(ep)
            
            # 2. 加载角色配置
            if os.path.exists(self.role_config_path):
                with open(self.role_config_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    self.roles = {k: RoleConfigV2(**v) for k, v in data.items()}
            
            logger.info(f"✅ [算力池] 已就绪: {len(self.pools)} 个池, {len(self.states)} 个接入点")
        except Exception as e:
            logger.error(f"加载池化配置失败: {e}")

    def select_best_endpoint(self, pool_id: str) -> Optional[EndpointConfig]:
        """[V66.0] 企业级路由：家族优先 + 跨平台调度 + 额度平滑"""
        pool = self.pools.get(pool_id)
        if not pool: return None

        now = time.time()
        
        # 1. 筛选可用节点并按家族分组
        family_groups: Dict[str, List[Tuple[EndpointConfig, float]]] = {}
        for ep in pool.endpoints:
            state = self.states.get(ep.id)
            if not state or (state.is_cooling and now < state.cooldown_until):
                continue
            
            is_safe, usage, quota, _ = usage_tracker.check_limit(ep.id)
            if not is_safe: continue

            # 计算得分 (权重 * 健康度 * 额度系数)
            state.refresh_stability()
            remaining_ratio = 1.0 - (usage / quota) if quota > 0 else 0
            quota_factor = 0.3 if remaining_ratio < 0.2 else (0.05 if remaining_ratio < 0.05 else 1.0)
            score = ep.weight * state.stability * quota_factor
            
            if score > 0:
                fam = ep.family or "default"
                if fam not in family_groups: family_groups[fam] = []
                family_groups[fam].append((ep, score))

        if not family_groups:
            if pool.fallback_pool:
                logger.warning(f"⚠️ [池化降级] 池 {pool_id} 家族全灭，转向 {pool.fallback_pool}")
                return self.select_best_endpoint(pool.fallback_pool)
            return None

        # 2. 策略：优先选择权重总和最高的家族 (保证“平台切换优先于模型切换”)
        # 找出平均权重最高的家族
        best_family = max(family_groups.keys(), key=lambda f: sum(c[1] for c in family_groups[f]))
        candidates = family_groups[best_family]

        # 3. 选择逻辑：默认随机，开启稳定路由后则选择最高分
        if os.getenv("AUDIT_STABLE_ROUTING", "false").lower() == "true":
            best_ep = max(candidates, key=lambda c: c[1])[0]
            logger.info(f"🎯 [StableRouting] 确定性选择最高分节点: {best_ep.id}")
            return best_ep

        # 4. 在选中的家族内按权重随机选择平台
        total_score = sum(c[1] for c in candidates)
        r = random.uniform(0, total_score)
        upto = 0
        for ep, score in candidates:
            if upto + score >= r:
                return ep
            upto += score
        
        return candidates[0][0]

    def record_failure(self, ep_id: str, reason: str):
        """[V66.0] 记录故障并进入冷却：支持 2 小时长封禁逻辑"""
        if ep_id in self.states:
            state = self.states[ep_id]
            state.is_cooling = True
            
            # [企业级策略] 针对 429/Quota 类错误执行 2 小时长效熔断
            is_quota_error = any(sig in reason.lower() for sig in ["429", "quota", "limit", "rate", "流量控制"])
            cooldown = 7200 if is_quota_error else 60
            
            state.cooldown_until = time.time() + cooldown
            logger.warning(f"⛔ [节点熔断] {ep_id} 进入 {'长效' if cooldown > 60 else '短效'} 观察期 ({cooldown}s): {reason}")
            usage_tracker.record_failure(ep_id, reason)

    def record_success(self, ep_id: str):
        """成功后解除冷却并恢复信心"""
        if ep_id in self.states:
            state = self.states[ep_id]
            if state.is_cooling:
                logger.info(f"✅ [节点复活] {ep_id} 提前解除封禁")
            state.is_cooling = False
            usage_tracker.record_success(ep_id)

# 单例导出
endpoint_pool_manager = EndpointPoolManager()
