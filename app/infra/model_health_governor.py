"""
app/infra/model_health_governor.py
==================================
[V4.9.15] 模型稳定性评分、物理熔断与自愈治理深模块
负责错误指纹审计、健康分衰减与回弹、临时冷却与 24 点物理封禁状态机。
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, Callable
from loguru import logger
from app.core.schemas import ModelConfig


class ModelHealthGovernor:
    """管理模型节点的健康分评级、黑名单过期状态与限额决策"""

    def __init__(
        self,
        model_configs: Dict[str, ModelConfig],
        blacklist_expiry: Dict[str, float],
        stability_scores: Dict[str, float],
    ):
        self.model_configs = model_configs
        self.blacklist_expiry = blacklist_expiry
        self.stability_scores = stability_scores

    def get_stability_score(self, model_id: str) -> float:
        """获取模型当前的健康评分 (0.0 ~ 1.0)"""
        return self.stability_scores.get(model_id, 1.0)

    def blacklist_model(
        self,
        model_id: str,
        reason: str,
        permanent: bool = False,
        on_persist: Optional[Callable[[], None]] = None,
    ) -> None:
        """将模型列入黑名单，设置过期时间与健康分惩罚"""
        if model_id in self.model_configs:
            cfg = self.model_configs[model_id]
            cfg.is_active = False
            cfg.last_error = reason

            if permanent or "403" in reason:
                # 物理熔断：精准封禁到当日 23:59:59
                now = datetime.now()
                eod = datetime(now.year, now.month, now.day) + timedelta(days=1) - timedelta(seconds=1)
                self.blacklist_expiry[model_id] = eod.timestamp()
                self.stability_scores[model_id] = 0.0
                logger.error(f"!!! [物理熔断] 节点 {model_id} 已当日强制下线并封禁直到24点 (原因: {str(reason)[:100]}...) !!!")
            elif "quota" in reason.lower() or "exhausted" in reason.lower():
                # 限额熔断：冷却 300 秒（5 分钟），等待配额周期重置
                new_expiry = time.time() + 300
                self.blacklist_expiry[model_id] = new_expiry
                self.stability_scores[model_id] = 0.2
                logger.warning(f"⚠️ [额度限制熔断] 节点 {model_id} 进入 5min 额度重置冷却期: {str(reason)[:100]}")
            else:
                # 临时冷却：2 分钟后尝试找回
                new_expiry = time.time() + 120
                if self.blacklist_expiry.get(model_id, 0) < new_expiry:
                    self.blacklist_expiry[model_id] = new_expiry
                logger.warning(f">>> [临时冷却] 节点 {model_id} 进入 2min 观察期: {reason}")

            if on_persist:
                on_persist()

    def record_failure(
        self,
        model_id: str,
        error_code: str,
        on_persist: Optional[Callable[[], None]] = None,
    ) -> None:
        """记录调用故障并根据错误等级扣减健康分或物理熔断"""
        # 指纹审计：检查报错信息中是否包含其它模型 ID (解决 Fallback 误伤问题)
        target_id = model_id
        for m_id in self.model_configs.keys():
            if m_id in error_code and m_id != model_id:
                logger.warning(f">>> [指纹审计] 发现报错实际指向模型: {m_id} (原始指向: {model_id})")
                target_id = m_id
                break

        # 铁腕治理：扩展错误判定范围，将“未找到模型(404)”和“额度暂停/超出限制”视为当日永久失效
        is_permanent_fail = any(k in error_code.lower() for k in [
            "403", "404", "quota", "exhausted", "free tier", "freetier",
            "not_found", "not found", "does not exist", "invalid_model", "model_not_found",
            "setlimitexceeded", "limitexceeded", "inference limit", "safe experience mode"
        ])

        if is_permanent_fail:
            reason = f"Critical Error: {error_code}"
            if "404" in error_code or "not found" in error_code.lower():
                reason = f"[模型不存在] 节点 {target_id} 在供应商端未找到，物理剔除。"
            self.blacklist_model(target_id, reason=reason, permanent=True, on_persist=on_persist)
            return

        current = self.get_stability_score(target_id)
        deduction = 0.2
        self.stability_scores[target_id] = max(0.0, current - deduction)
        if on_persist:
            on_persist()
        logger.warning(f"!!! [健康降级] 节点 {target_id} 稳定性扣分: {current:.2f} -> {self.stability_scores[target_id]:.2f}")

    def record_success(
        self,
        model_id: str,
        on_persist: Optional[Callable[[], None]] = None,
    ) -> None:
        """成功后缓慢回弹健康分，并清除黑名单实现自愈"""
        current = self.get_stability_score(model_id)
        self.stability_scores[model_id] = min(1.0, current + 0.1)

        if model_id in self.blacklist_expiry:
            self.blacklist_expiry.pop(model_id, None)
            logger.info(f"💖 [自愈成功] 物理节点 {model_id} 已从每日黑名单中自动解除封禁！")
        if model_id in self.model_configs:
            cfg = self.model_configs[model_id]
            cfg.is_active = True
            cfg.last_error = None

        if on_persist:
            on_persist()

    def check_limit(
        self,
        model_id: str,
        daily_usage: int,
        daily_requests: int,
        current_rpm: int,
        current_tpm: int,
        on_persist: Optional[Callable[[], None]] = None,
    ) -> Tuple[bool, int, int, str]:
        """
        检查模型是否受限（包含黑名单到期自动解除机制、日额度、RPD、RPM、TPM）
        Returns: (allowed, current_metric, limit, message)
        """
        model_cfg = self.model_configs.get(model_id)
        if not model_cfg:
            return True, 0, 0, "未知模型，静默放行"

        # 黑名单到期自动解除检查
        now = time.time()
        if not model_cfg.is_active:
            expiry = self.blacklist_expiry.get(model_id, 0)
            if now > expiry:
                model_cfg.is_active = True
                self.blacklist_expiry.pop(model_id, None)
                if on_persist:
                    on_persist()
                logger.info(f"✅ [黑名单到期] 模型 {model_id} 拉黑已自动解除，重新就绪。")
            else:
                remaining = int(expiry - now)
                return False, 0, 0, f"模型 [{model_id}] 临时拉黑中，还有 {remaining} 秒自动解除"
        elif model_id in self.blacklist_expiry:
            expiry = self.blacklist_expiry[model_id]
            if now > expiry:
                self.blacklist_expiry.pop(model_id, None)
                if on_persist:
                    on_persist()
            else:
                model_cfg.is_active = False
                remaining = int(expiry - now)
                return False, 0, 0, f"模型 [{model_id}] 仍然处于封禁状态中，还有 {remaining} 秒自动解除"

        # 1. 每日 Token 额度校验
        if daily_usage >= model_cfg.daily_quota:
            return False, daily_usage, model_cfg.daily_quota, "每日 Token 额度耗尽"

        # 2. RPD (Requests Per Day) 校验
        if daily_requests >= model_cfg.rpd_limit:
            return False, daily_requests, model_cfg.rpd_limit, "每日请求数 (RPD) 已超限"

        # 3. RPM (Requests Per Minute) 校验
        if current_rpm >= model_cfg.rpm_limit:
            return False, current_rpm, model_cfg.rpm_limit, f"分钟请求剧烈 (RPM:{current_rpm})，进入物理冷却"

        # 4. TPM (Tokens Per Minute) 校验
        if current_tpm >= model_cfg.tpm_limit:
            return False, current_tpm, model_cfg.tpm_limit, f"分钟吐吐过载 (TPM:{current_tpm})，进入物理冷却"

        return True, daily_usage, model_cfg.daily_quota, "配额充足"

    def reset_blacklists(self, on_persist: Optional[Callable[[], None]] = None) -> None:
        """强制重置全部黑名单"""
        logger.info(">>> [算力治理] 正在执行全量黑名单清零，重启算力寻回流程。")
        self.blacklist_expiry.clear()
        for cfg in self.model_configs.values():
            cfg.is_active = True
            cfg.last_error = None
        if on_persist:
            on_persist()
