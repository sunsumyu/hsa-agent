import os
import json
import time
import random
import sqlite3
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
        """加载池化配置并执行增量数据库同步 [V178.9]"""
        try:
            import hashlib
            from datetime import datetime
            from app.core.memory.manager import memory_hub
            
            # 1. 加载并同步池配置
            if os.path.exists(self.pool_config_path):
                with open(self.pool_config_path, 'r', encoding='utf-8-sig') as f:
                    raw_content = f.read()
                    data = json.loads(raw_content)
                    
                    # 增量哈希校验
                    current_hash = hashlib.md5(raw_content.encode()).hexdigest()
                    db = memory_hub.relational_storage
                    
                    need_sync = True
                    with sqlite3.connect(db.db_path) as conn:
                        res = conn.execute("SELECT last_hash FROM config_meta WHERE config_name='endpoint_pools'").fetchone()
                        if res and res[0] == current_hash:
                            need_sync = False
                    
                    for p_id, p_cfg in data.get("pools", {}).items():
                        pool = PoolConfig(**p_cfg)
                        self.pools[p_id] = pool
                        for ep in pool.endpoints:
                            if ep.id not in self.states:
                                self.states[ep.id] = EndpointState(ep)
                            
                            # 执行增量数据库同步
                            if need_sync:
                                with sqlite3.connect(db.db_path) as conn:
                                    conn.execute("""
                                        INSERT OR REPLACE INTO endpoint_configs 
                                        (id, pool_id, platform, model_name, weight, status, last_sync)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (ep.id, p_id, ep.platform, ep.model_name, ep.weight, "ACTIVE", datetime.now().isoformat()))
                    
                    if need_sync:
                        with sqlite3.connect(db.db_path) as conn:
                            conn.execute("INSERT OR REPLACE INTO config_meta VALUES (?, ?, ?)", 
                                       ("endpoint_pools", current_hash, datetime.now().isoformat()))
                        logger.info("📡 [Sync] 配置已发生变更，已完成数据库增量同步。")
            
            # [V200.0] 动态同步云端推理接入点配置
            self.sync_volcengine_endpoints()
            
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
    
    def get_endpoint_config(self, ep_id: str) -> Optional[EndpointConfig]:
        """[V178.9] 根据 ID 获取接入点静态配置"""
        state = self.states.get(ep_id)
        return state.config if state else None

    def record_failure(self, ep_id: str, reason: str):
        """[V66.0] 记录故障并进入冷却：支持 2 小时长封禁逻辑"""
        if ep_id in self.states:
            state = self.states[ep_id]
            state.is_cooling = True
            
            # [企业级策略] 针对 429/Quota 类错误执行 2 小时长效熔断
            is_quota_error = any(sig in reason.lower() for sig in ["429", "quota", "limit", "rate", "流量控制"])
            cooldown = 7200 if is_quota_error else 60
            
            state.cooldown_until = time.time() + cooldown
            disp_name = self.get_endpoint_display_name(ep_id)
            logger.warning(f"⛔ [节点熔断] {disp_name} 进入 {'长效' if cooldown > 60 else '短效'} 观察期 ({cooldown}s): {str(reason)[:100]}...")
            usage_tracker.record_failure(ep_id, reason)

    def record_success(self, ep_id: str):
        """成功后解除冷却并恢复信心"""
        if ep_id in self.states:
            state = self.states[ep_id]
            if state.is_cooling:
                disp_name = self.get_endpoint_display_name(ep_id)
                logger.info(f"✅ [节点复活] {disp_name} 提前解除封禁")
            state.is_cooling = False
            usage_tracker.record_success(ep_id)

    def get_endpoint_display_name(self, ep_id: str) -> str:
        """获取接入点的人类可读显示名（优先云端拉取的名称）"""
        state = self.states.get(ep_id)
        if state and state.config.display_name:
            return state.config.display_name
        return ep_id

    def sync_volcengine_endpoints(self):
        """[V200.0] 利用 IAM 秘钥，动态同步火山引擎的真实接入点名称与模型底座"""
        ak = os.getenv("VOLC_ACCESS_KEY")
        sk = os.getenv("VOLC_SECRET_KEY")
        if not ak or not sk:
            logger.info("ℹ️ [云端同步] 未配置 VOLC_ACCESS_KEY/VOLC_SECRET_KEY，跳过动态接入点同步")
            return

        try:
            import volcenginesdkcore
            import volcenginesdkark
            
            logger.info("🔄 [云端同步] 正在从火山引擎动态同步推理接入点...")
            configuration = volcenginesdkcore.Configuration()
            configuration.ak = ak
            configuration.sk = sk
            configuration.region = "cn-beijing"
            
            api_instance = volcenginesdkark.ARKApi(volcenginesdkcore.ApiClient(configuration))
            req = volcenginesdkark.ListEndpointsRequest()
            resp = api_instance.list_endpoints(req)
            
            if not resp.items:
                logger.info("ℹ️ [云端同步] 火山引擎未查询到任何推理接入点")
                return
                
            remote_endpoints = {}
            for item in resp.items:
                foundation_model = "unknown"
                if hasattr(item, 'model_reference') and item.model_reference:
                    ref = item.model_reference
                    if hasattr(ref, 'foundation_model') and ref.foundation_model:
                        fm = ref.foundation_model
                        if isinstance(fm, dict):
                            foundation_model = fm.get('name', 'unknown')
                        elif hasattr(fm, 'name'):
                            foundation_model = fm.name
                
                name = item.name
                try:
                    if isinstance(name, str):
                        # 尝试将 latin1 编码的乱码还原为 UTF-8
                        name = name.encode('latin1').decode('utf-8')
                except Exception:
                    pass
                
                remote_endpoints[item.id] = {
                    "name": name,
                    "foundation_model": foundation_model
                }
                
            logger.info(f"✅ [云端同步] 成功同步 {len(remote_endpoints)} 个火山推理接入点: {list(remote_endpoints.keys())}")
            
            # 动态更新本地路由池与模型映射
            for pool in self.pools.values():
                for ep in pool.endpoints:
                    if ep.platform == "volcengine" and ep.model_name in remote_endpoints:
                        info = remote_endpoints[ep.model_name]
                        logger.info(f"🔄 [动态对齐] 本地配置 ID: {ep.id} -> 动态拉取名称: {info['name']} | 底座: {info['foundation_model']}")
                        
                        # 动态更新 Endpoint 属性
                        ep.display_name = info['name']
                        if info['foundation_model'] != 'unknown':
                            ep.family = info['foundation_model']
                            
        except Exception as e:
            logger.warning(f"⚠️ [云端同步] 动态同步火山接入点失败: {e}")

# 单例导出
endpoint_pool_manager = EndpointPoolManager()
