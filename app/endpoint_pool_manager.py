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
    def __init__(self, pool_config_path="app/endpoint_pools.json", 
                       role_config_path="app/role_configs.json"):
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
                with open(self.pool_config_path, 'r', encoding='utf-8') as f:
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
                with open(self.role_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.roles = {k: RoleConfigV2(**v) for k, v in data.items()}
            
            logger.info(f"✅ [算力池] 已就绪: {len(self.pools)} 个池, {len(self.states)} 个接入点")
        except Exception as e:
            logger.error(f"加载池化配置失败: {e}")

    def select_best_endpoint(self, pool_id: str) -> Optional[EndpointConfig]:
        """核心路由算法：加权 + 健康感知 + 额度平滑"""
        pool = self.pools.get(pool_id)
        if not pool:
            return None

        logger.debug(f">>> [路由诊断] 池 ID: {pool_id} | 节点数: {len(pool.endpoints)} | 状态机节点: {list(self.states.keys())}")
        candidates: List[Tuple[EndpointConfig, float]] = []
        now = time.time()
        for ep in pool.endpoints:
            state = self.states.get(ep.id)
            if not state: 
                logger.debug(f"--- [路由跳过] 节点 {ep.id} 在状态机中不存在")
                continue

            # 1. 物理拦截：冷却中或配额已尽
            if state.is_cooling and now < state.cooldown_until:
                logger.debug(f"--- [路由跳过] 节点 {ep.id} 正在冷却中")
                continue
            
            is_safe, usage, quota, reason = usage_tracker.check_limit(ep.id)
            if not is_safe:
                logger.debug(f"--- [路由跳过] 节点 {ep.id} 不可用: {reason}")
                continue

            # 2. 计算综合得分
            # 基础权重 (weight)
            base_weight = ep.weight
            
            # 健康系数 (stability: 0.0~1.0)
            state.refresh_stability()
            health_factor = state.stability
            
            # 额度平滑系数 (剩余 20% 时开始降权)
            remaining_ratio = 1.0 - (usage / quota) if quota > 0 else 0
            quota_factor = 1.0
            if remaining_ratio < 0.2:
                quota_factor = 0.3  # 剩余不足 20%，降权至 30% 流量
            if remaining_ratio < 0.05:
                quota_factor = 0.05 # 临近枯竭，仅保留 5% 流量探测

            # 最终得分 = 权重 * 健康度 * 额度系数
            score = base_weight * health_factor * quota_factor
            
            logger.debug(f"--- [打分计算] 节点: {ep.id} | Base: {base_weight} | Health: {health_factor:.2f} | QuotaFactor: {quota_factor:.2f} | FinalScore: {score:.2f}")
            
            if score > 0:
                candidates.append((ep, score))

        if not candidates:
            # 如果当前池全部失效，尝试降级到 fallback 池
            if pool.fallback_pool:
                logger.warning(f"⚠️ [池化降级] 池 {pool_id} 无可用节点，正在转向 {pool.fallback_pool}...")
                return self.select_best_endpoint(pool.fallback_pool)
            return None

        # 3. 按权重概率随机选择 (类似加权轮询)
        total_score = sum(c[1] for c in candidates)
        r = random.uniform(0, total_score)
        upto = 0
        for ep, score in candidates:
            if upto + score >= r:
                return ep
            upto += score
        
        return candidates[0][0]

    def record_failure(self, ep_id: str, reason: str):
        """记录故障并进入冷却"""
        if ep_id in self.states:
            state = self.states[ep_id]
            state.is_cooling = True
            # 根据错误严重程度设置冷却时间 (30s ~ 300s)
            cooldown = 300 if "403" in reason or "quota" in reason.lower() else 60
            state.cooldown_until = time.time() + cooldown
            logger.warning(f"⛔ [节点冷却] {ep_id} 进入 {cooldown}s 观察期: {reason}")
            usage_tracker.record_failure(ep_id, reason)

    def record_success(self, ep_id: str):
        """成功后解除冷却并恢复信心"""
        if ep_id in self.states:
            state = self.states[ep_id]
            state.is_cooling = False
            usage_tracker.record_success(ep_id)

# 单例导出
endpoint_pool_manager = EndpointPoolManager()
