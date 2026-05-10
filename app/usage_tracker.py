import json
import os
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, List, Optional, Union, Any
from app.schemas import ModelConfig, UsageStats, RoleConfigV2, AgentRole

class UsageTracker:
    def __init__(self, stats_path="data/usage_stats.json", config_path="app/endpoint_pools.json", role_path="app/role_configs.json"):
        self.stats_path = stats_path
        self.config_path = config_path
        self.role_path = role_path
        self._ensure_dir()
        self.stats: UsageStats = self._load_stats()
        self.model_configs: Dict[str, ModelConfig] = self._load_model_configs()
        self.role_configs: Dict[str, RoleConfigV2] = self._load_role_configs()
        # [V4.9.6] 内存窗口：追踪分钟级指标 (RPM, TPM)
        self.rpm_window: Dict[str, Dict[str, int]] = {} # {model_id: {minute: count}}
        self.tpm_window: Dict[str, Dict[str, int]] = {} # {model_id: {minute: tokens}}
        # [V4.9.12] 黑名单过期机制：从 stats 中引用以支持持久化
        self.blacklist_expiry: Dict[str, float] = self.stats.blacklist_expiry # {model_id: expiry_timestamp}
        # [V4.9.15] 架构稳定性加固：记录各节点的健康分 (0.0 - 1.0)
        self.stability_scores: Dict[str, float] = self.stats.stability_scores # {model_id: score}

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.stats_path), exist_ok=True)

    def _get_current_minute(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _prune_windows(self):
        """清理过期窗口数据（保留最近 5 分钟以供观察）"""
        now = self._get_current_minute()
        for window in [self.rpm_window, self.tpm_window]:
            for model_id in list(window.keys()):
                minutes = list(window[model_id].keys())
                for m in minutes:
                    if m != now: # 简化版：仅保留当前分钟，或可根据需求扩展
                        del window[model_id][m]

    def _load_model_configs(self) -> Dict[str, ModelConfig]:
        """[V50.0] 从算力池配置中提取所有 Endpoint 的模型定义"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    all_endpoints = {}
                    for p_id, p_cfg in data.get("pools", {}).items():
                        for ep in p_cfg.get("endpoints", []):
                            # 将 EndpointConfig 的字典转换为 ModelConfig 以保持兼容
                            all_endpoints[ep["id"]] = ModelConfig(**ep)
                    return all_endpoints
        except Exception as e:
            logger.error(f"加载模型配置失败: {e}")
        return {}

    def _load_role_configs(self) -> Dict[str, RoleConfigV2]:
        """[V35.0] 加载角色模型映射与预算配置"""
        try:
            if os.path.exists(self.role_path):
                with open(self.role_path, 'r', encoding='utf-8-sig') as f:
                    raw_data = json.load(f)
                    return {k: RoleConfigV2(**v) for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"加载角色配置失败: {e}")
        return {}

    def _load_stats(self) -> UsageStats:
        """[V4.9.0] 架构升级：使用 Pydantic 实现用量统计的结构化管理"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(self.stats_path):
            try:
                with open(self.stats_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    stats = UsageStats(**data)
                    
                    if stats.today != today_str:
                        logger.info(f"新的一天 ({today_str})，正在执行指标归位并保存状态。")
                        stats.today = today_str
                        stats.daily_usage = {}
                        stats.daily_requests = {}
                        stats.blacklist_expiry.clear()
                        stats.stability_scores.clear()
                        # [V4.9.11] 物理加固：日期重置后立即刷新磁盘，防止前端读取到旧日期文件
                        with open(self.stats_path, 'w', encoding='utf-8') as sf:
                            sf.write(stats.model_dump_json(indent=2))
                        # [V4.9.12] 日期探到新天：全量解除黑名单，重置模型活跃状态
                        if hasattr(self, 'model_configs'):
                            for cfg in self.model_configs.values():
                                cfg.is_active = True
                        logger.info("✅ [新日自愈] 全量黑名单已自动清除，所有模型重新就绪。")
                    
                    # 恢复配置对象的 is_active 状态 (重启后内存被置回True，根据持久化数据修正)
                    return stats
            except Exception as e:
                logger.error(f"加载用量统计失败: {e}")
        
        return UsageStats(today=today_str)

    def _save_stats(self):
        try:
            with open(self.stats_path, 'w', encoding='utf-8') as f:
                # 使用 Pydantic 的 model_dump_json 确保序列化正确
                f.write(self.stats.model_dump_json(indent=2))
        except Exception as e:
            logger.error(f"保存用量统计失败: {e}")

    def _estimate_tokens(self, text: Any) -> int:
        """[V6.0] 工业级 Token 估算器 (物理校准版)"""
        if not text: return 0
        # [V58.7] 容错处理：确保转为字符串，防止直接传入 Message 对象列表导致 '<=' 报错
        text_str = str(text)
        # 汉字 count * 1.5 + 英文 count * 0.4 (基于 tiktoken 对中文支持较差的物理适配)
        zh_count = len([c for c in text_str if '\u4e00' <= c <= '\u9fff'])
        en_count = len(text_str) - zh_count
        return int(zh_count * 1.5 + en_count * 0.4)

    def record_usage(self, model_id: str, input_tokens: int, output_tokens: int, prompt: str = "", response_text: str = ""):
        # [V6.1.0] 物理主权恢复：如果获取不到 Token 数，执行强力内容估算
        if input_tokens == 0 and prompt:
            input_tokens = self._estimate_tokens(prompt)
            # logger.debug(f">>> [用量校准] Input 估算: {input_tokens} t")
            
        if output_tokens == 0 and response_text:
            output_tokens = self._estimate_tokens(response_text)
            # logger.debug(f">>> [用量校准] Output 估算: {output_tokens} t")
            
        if input_tokens == 0 and output_tokens == 0:
            # 如果依然为 0 且没传文本，标记警告
            logger.warning(f">>> [用量异常] 模型 {model_id} 未返回 Meta 且未传入文本供估算，统计维持 0 点。")
            
        total = input_tokens + output_tokens
        current_min = self._get_current_minute()
        
        # 1. 更新持久化统计 (RPD, Daily Tokens, Total Tokens)
        self.stats.daily_usage[model_id] = self.stats.daily_usage.get(model_id, 0) + total
        self.stats.daily_requests[model_id] = self.stats.daily_requests.get(model_id, 0) + 1
        self.stats.total_usage[model_id] = self.stats.total_usage.get(model_id, 0) + total
        self._save_stats()
        
        # 2. 更新内存窗口 (RPM, TPM)
        if model_id not in self.rpm_window: self.rpm_window[model_id] = {}
        if model_id not in self.tpm_window: self.tpm_window[model_id] = {}
        
        self.rpm_window[model_id][current_min] = self.rpm_window[model_id].get(current_min, 0) + 1
        self.tpm_window[model_id][current_min] = self.tpm_window[model_id].get(current_min, 0) + total
        
        self._prune_windows()

        # 估算计费
        model_cfg = self.model_configs.get(model_id)
        if model_cfg:
            i_cost = (input_tokens / 1000) * model_cfg.input_cost_1k
            o_cost = (output_tokens / 1000) * model_cfg.output_cost_1k
            total_cost = i_cost + o_cost
            rpd = self.stats.daily_requests[model_id]
            rpm = self.rpm_window[model_id][current_min]
            logger.info(f"用量流水: {model_id} | +{total} tokens (含估算) | RPD:{rpd} | RPM:{rpm} | 计费: ${total_cost:.4f}")

    def check_limit(self, model_id: str):
        """
        [V4.9.12] 升级版：黑名单支持自动过期解除
        """
        import time
        model_cfg = self.model_configs.get(model_id)
        if not model_cfg:
            return True, 0, 0, "未知模型，静默放行"

        # [V4.9.12] 黑名单过期自动解除检查
        if not model_cfg.is_active:
            expiry = self.blacklist_expiry.get(model_id, 0)
            if time.time() > expiry:
                # 到期了，自动解除拉黑
                model_cfg.is_active = True
                self.blacklist_expiry.pop(model_id, None)
                self._save_stats()
                logger.info(f"✅ [黑名单到期] 模型 {model_id} 拉黑已自动解除，重新就绪。")
            else:
                remaining = int(expiry - time.time())
                return False, 0, 0, f"模型 [{model_id}] 临时拉黑中，还有 {remaining} 秒自动解除"
        # 补充：刚启动程序时内存里 is_active 是 True，但持久化里可能已被封禁
        elif model_id in self.blacklist_expiry:
            expiry = self.blacklist_expiry[model_id]
            if time.time() > expiry:
                self.blacklist_expiry.pop(model_id, None)
                self._save_stats()
            else:
                model_cfg.is_active = False
                remaining = int(expiry - time.time())
                return False, 0, 0, f"模型 [{model_id}] 仍然处于封禁状态中，还有 {remaining} 秒自动解除"

        current_min = self._get_current_minute()

        # 1. 每日 Token 额度校验
        usage = self.stats.daily_usage.get(model_id, 0)
        if usage >= model_cfg.daily_quota:
            return False, usage, model_cfg.daily_quota, "每日 Token 额度耗尽"

        # 2. RPD (Requests Per Day) 校验
        rpd = self.stats.daily_requests.get(model_id, 0)
        if rpd >= model_cfg.rpd_limit:
            return False, rpd, model_cfg.rpd_limit, "每日请求数 (RPD) 已超限"

        # 3. RPM (Requests Per Minute) 校验
        rpm = self.rpm_window.get(model_id, {}).get(current_min, 0)
        if rpm >= model_cfg.rpm_limit:
            return False, rpm, model_cfg.rpm_limit, f"分钟请求剧烈 (RPM:{rpm})，进入物理冷却"

        # 4. TPM (Tokens Per Minute) 校验
        tpm = self.tpm_window.get(model_id, {}).get(current_min, 0)
        if tpm >= model_cfg.tpm_limit:
            return False, tpm, model_cfg.tpm_limit, f"分钟吐吐过载 (TPM:{tpm})，进入物理冷却"

        return True, usage, model_cfg.daily_quota, "配额充足"

    def check_role_budget(self, role: str, input_tokens: int, output_tokens: int):
        """
        [V35.0] 角色级预算拦截：防止单智能体 Token 异常膨胀。
        规则：不能超过正常水平的 2 倍。
        """
        role_cfg = self.role_configs.get(role)
        if not role_cfg:
            return True, ""

        # 检查 Input 预算
        if input_tokens > role_cfg.max_input_tokens * 2:
             return False, f"角色 [{role}] 输入 Token ({input_tokens}) 严重超限 (上限 {role_cfg.max_input_tokens * 2})"
        
        # 检查 Output 预算
        if output_tokens > role_cfg.max_output_tokens * 2:
             return False, f"角色 [{role}] 输出 Token ({output_tokens}) 严重超限 (上限 {role_cfg.max_output_tokens * 2})"

        return True, ""

    def get_role_config(self, role: str) -> Optional[RoleConfigV2]:
        return self.role_configs.get(role)

    def blacklist_model(self, model_id: str, reason: str, permanent: bool = False):
        """[V5.2.0] 硬熔断功能：将物理额度耗尽(403)的模型彻底踢出当日寻址链路"""
        import time
        if model_id in self.model_configs:
            cfg = self.model_configs[model_id]
            cfg.is_active = False
            cfg.last_error = reason
            
            if permanent or "403" in reason or "Quota" in reason or "exhausted" in reason.lower():
                # 物理熔断：精准封禁到当日 23:59:59
                now = datetime.now()
                eod = datetime(now.year, now.month, now.day) + timedelta(days=1) - timedelta(seconds=1)
                self.blacklist_expiry[model_id] = eod.timestamp()
                self.stability_scores[model_id] = 0.0
                logger.error(f"!!! [物理熔断] 节点 {model_id} 已当日强制下线并封禁直到24点: {reason} !!!")
            else:
                # 临时冷却：2 分钟后尝试找回
                new_expiry = time.time() + 120
                if self.blacklist_expiry.get(model_id, 0) < new_expiry:
                    self.blacklist_expiry[model_id] = new_expiry
                logger.warning(f">>> [临时冷却] 节点 {model_id} 进入 2min 观察期: {reason}")
            
            # 立即持久化状态
            self._save_stats()

    def should_run_startup_probe(self) -> bool:
        """检查今日是否已经执行过全量自检"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.stats.last_probe_date != today_str:
            self.stats.last_probe_date = today_str
            self._save_stats()
            return True
        return False

    def get_stability_score(self, model_id: str) -> float:
        return self.stability_scores.get(model_id, 1.0)

    def record_failure(self, model_id: str, error_code: str):
        """记录故障并扣除健康分"""
        # [V5.6.1] 指纹审计：检查报错信息中是否包含其它模型 ID (解决 Fallback 误伤问题)
        target_id = model_id
        for m_id in self.model_configs.keys():
            if m_id in error_code and m_id != model_id:
                logger.warning(f">>> [指纹审计] 发现报错实际指向模型: {m_id} (原始指向: {model_id})")
                target_id = m_id
                break

        # [V5.6.0] 铁腕治理：扩展错误判定范围，将“未找到模型(404)”视为当日永久失效
        is_permanent_fail = any(k in error_code.lower() for k in [
            "403", "404", "quota", "exhausted", "free tier", "freetier", 
            "not_found", "not found", "does not exist", "invalid_model", "model_not_found"
        ])
        
        if is_permanent_fail:
            reason = f"Critical Error: {error_code}"
            # 如果是 404，特别标注其性质
            if "404" in error_code or "not found" in error_code.lower():
                reason = f"[模型不存在] 节点 {target_id} 在供应商端未找到，物理剔除。"
                
            self.blacklist_model(target_id, reason=reason, permanent=True)
            return

        current = self.get_stability_score(target_id)
        deduction = 0.2
        self.stability_scores[target_id] = max(0.0, current - deduction)
        self._save_stats()
        logger.warning(f"!!! [健康降级] 节点 {target_id} 稳定性扣分: {current:.2f} -> {self.stability_scores[target_id]:.2f}")

    def record_success(self, model_id: str):
        """成功后缓慢恢复健康分"""
        current = self.get_stability_score(model_id)
        self.stability_scores[model_id] = min(1.0, current + 0.1)
        self._save_stats()


    def reset_blacklists(self):
        """[V4.9.14] 强制重置：用于紧急恢复算力链路"""
        logger.info(">>> [算力治理] 正在执行全量黑名单清零，重启算力寻回流程。")
        self.blacklist_expiry.clear()
        for cfg in self.model_configs.values():
            cfg.is_active = True
            cfg.last_error = None

    def get_usage_report(self) -> str:
        """[V37.4] 生成今日用量统计报告。"""
        report = ["\n--- 今日算力消耗报告 ---"]
        for m_id, tokens in self.stats.daily_usage.items():
            reqs = self.stats.daily_requests.get(m_id, 0)
            report.append(f"- {m_id}: {tokens} tokens | {reqs} requests")
        return "\n".join(report)

# 全局单例
usage_tracker = UsageTracker()
