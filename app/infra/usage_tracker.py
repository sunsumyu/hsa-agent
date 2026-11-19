"""
app/infra/usage_tracker.py
==========================
[V4.9.0 / Matt Pocock Deep Module] 算力用量追踪与全局治理中枢
提供模型调用消耗统计、Token 估算、分钟级流量窗口与物理熔断治理。
底层组合 UsageWindowTracker 与 ModelHealthGovernor 两大专职深模块。

并发契约 (P0-1 锁收敛): governor 按引用持有 stats.blacklist_expiry /
stats.stability_scores 同一份 dict, 而 _save_stats 会迭代序列化这些 dict。
因此所有触碰共享状态的写路径 (含委托 governor 的方法与持久化) 必须收敛到
self._lock 单一互斥域; governor 本身保持无锁 (它是被保护的内部协作者)。
只读报表 getter 在锁内取 dict 快照后于锁外计算, 避免迭代期间被写路径改写。
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from loguru import logger

from app.core.schemas import ModelConfig, UsageStats, RoleConfigV2
from app.infra.usage_window_tracker import UsageWindowTracker
from app.infra.model_health_governor import ModelHealthGovernor


class UsageTracker:
    """算力用量追踪与模型运行治理门面深模块"""

    def __init__(
        self,
        stats_path: str = "data/usage_stats.json",
        config_path: str = "configs/endpoint_pools.json",
        role_path: str = "configs/role_configs.json",
    ):
        self.stats_path = stats_path
        self.config_path = config_path
        self.role_path = role_path
        self._ensure_dir()

        self.stats: UsageStats = self._load_stats()
        self.cloud_remaining_tokens: Dict[str, int] = {}
        self._model_configs: Dict[str, ModelConfig] = self._load_model_configs()
        self.role_configs: Dict[str, RoleConfigV2] = self._load_role_configs()

        self._lock = threading.Lock()

        # 组合专职深模块：时序滑动窗口与延迟画像
        self._window_tracker = UsageWindowTracker()
        self.rpm_window = self._window_tracker.rpm_window
        self.tpm_window = self._window_tracker.tpm_window
        self.latency_window = self._window_tracker.latency_window

        # 组合专职深模块：稳定性评分与物理熔断治理
        self._governor = ModelHealthGovernor(
            model_configs=self._model_configs,
            blacklist_expiry=self.stats.blacklist_expiry,
            stability_scores=self.stats.stability_scores,
        )

    @property
    def model_configs(self) -> Dict[str, ModelConfig]:
        return self._model_configs

    @model_configs.setter
    def model_configs(self, val: Dict[str, ModelConfig]):
        self._model_configs = val
        if hasattr(self, "_governor"):
            self._governor.model_configs = val

    @property
    def stability_scores(self) -> Dict[str, float]:
        return self.stats.stability_scores

    @stability_scores.setter
    def stability_scores(self, val: Dict[str, float]):
        self.stats.stability_scores = val
        if hasattr(self, "_governor"):
            self._governor.stability_scores = val

    @property
    def blacklist_expiry(self) -> Dict[str, float]:
        return self.stats.blacklist_expiry

    @blacklist_expiry.setter
    def blacklist_expiry(self, val: Dict[str, float]):
        self.stats.blacklist_expiry = val
        if hasattr(self, "_governor"):
            self._governor.blacklist_expiry = val

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.stats_path), exist_ok=True)

    def _get_current_minute(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _prune_windows(self):
        """清理过期窗口数据"""
        self._window_tracker.prune(self._get_current_minute())

    def _load_model_configs(self) -> Dict[str, ModelConfig]:
        """从算力池配置中提取所有 Endpoint 的模型定义，并合并云端全量数据"""
        all_endpoints = {}
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    for _, p_cfg in data.get("pools", {}).items():
                        for ep in p_cfg.get("endpoints", []):
                            all_endpoints[ep["id"]] = ModelConfig(**ep)
        except Exception as e:
            logger.error(f"加载模型配置失败: {e}")

        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(self.stats_path), "cloud_discovery.db")
            if os.path.exists(db_path):
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, platform, remaining FROM models")
                    for name, platform, remaining in cursor.fetchall():
                        if name not in all_endpoints:
                            rem = 0
                            try:
                                rem = int(remaining.replace(",", ""))
                            except Exception:
                                pass
                            all_endpoints[name] = ModelConfig(
                                provider=platform if platform else "unknown",
                                model_name=name,
                                family=name,
                                platform=platform,
                                api_key_env="UNKNOWN",
                                daily_quota=rem if rem > 0 else 1000000,
                            )
                            self.cloud_remaining_tokens[name] = rem
        except Exception as e:
            logger.error(f"加载 cloud_discovery.db 失败: {e}")

        return all_endpoints

    def _load_role_configs(self) -> Dict[str, RoleConfigV2]:
        """加载角色模型映射与预算配置"""
        try:
            if os.path.exists(self.role_path):
                with open(self.role_path, "r", encoding="utf-8-sig") as f:
                    raw_data = json.load(f)
                    return {k: RoleConfigV2(**v) for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"加载角色配置失败: {e}")
        return {}

    def _load_stats(self) -> UsageStats:
        """结构化管理用量统计，自动检测新天并重置黑名单与活跃状态"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(self.stats_path):
            try:
                with open(self.stats_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    stats = UsageStats(**data)

                    if stats.today != today_str:
                        logger.info(f"新的一天 ({today_str})，正在执行指标归位并保存状态。")
                        stats.today = today_str
                        stats.daily_usage = {}
                        stats.daily_requests = {}
                        stats.blacklist_expiry.clear()
                        stats.stability_scores.clear()
                        with open(self.stats_path, "w", encoding="utf-8") as sf:
                            sf.write(stats.model_dump_json(indent=2))
                        if hasattr(self, "model_configs"):
                            for cfg in self.model_configs.values():
                                cfg.is_active = True
                        logger.info("✅ [新日自愈] 全量黑名单已自动清除，所有模型重新就绪。")

                    return stats
            except Exception as e:
                logger.error(f"加载用量统计失败: {e}")

        return UsageStats(today=today_str)

    def _save_stats(self):
        """持久化用量统计至磁盘 (os.replace 原子替换，杜绝半包断裂)"""
        try:
            tmp_path = f"{self.stats_path}.tmp.{os.getpid()}_{time.time_ns()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(self.stats.model_dump_json(indent=2))
            os.replace(tmp_path, self.stats_path)
        except Exception as e:
            logger.error(f"保存用量统计失败: {e}")

    def _estimate_tokens(self, text: Any) -> int:
        """Token 估算器 (物理校准版)"""
        if not text:
            return 0
        text_str = str(text)
        zh_count = len([c for c in text_str if "\u4e00" <= c <= "\u9fff"])
        en_count = len(text_str) - zh_count
        return int(zh_count * 1.5 + en_count * 0.4)

    def get_burnout_prediction(self, model_id: str) -> int:
        """预测算力枯竭：计算当前配额还能支持几轮完整审计测试"""
        config = self.model_configs.get(model_id)
        if not config or not config.daily_quota:
            return 999
        current_usage = self.stats.daily_usage.get(model_id, 0)
        remaining_tokens = max(0, config.daily_quota - current_usage)
        TOKENS_PER_ROUND = 4500
        return int(remaining_tokens // TOKENS_PER_ROUND)

    def calibrate_usage(self, model_id: str, cloud_usage: int):
        """云端校准：使用云端真实用量覆盖本地估算值 (写路径收敛到锁内)"""
        with self._lock:
            old_usage = self.stats.daily_usage.get(model_id, 0)
            self.stats.daily_usage[model_id] = cloud_usage
            logger.info(f"📊 [Calibration] 模型 {model_id} 已校准: {old_usage} -> {cloud_usage}")
            self._save_stats()

    def record_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        prompt: str = "",
        response_text: str = "",
        latency_ms: float = 0,
    ):
        """核心审计指标记录 (线程安全锁保护)"""
        with self._lock:
            if input_tokens == 0 and prompt:
                input_tokens = self._estimate_tokens(prompt)
            if output_tokens == 0 and response_text:
                output_tokens = self._estimate_tokens(response_text)
            if input_tokens == 0 and output_tokens == 0:
                logger.warning(f">>> [用量异常] 模型 {model_id} 未返回 Meta 且未传入文本供估算，统计维持 0 点。")

            total = input_tokens + output_tokens
            current_min = self._get_current_minute()

            # 1. 持久化统计
            self.stats.daily_usage[model_id] = self.stats.daily_usage.get(model_id, 0) + total
            self.stats.daily_requests[model_id] = self.stats.daily_requests.get(model_id, 0) + 1
            self.stats.total_usage[model_id] = self.stats.total_usage.get(model_id, 0) + total
            self._save_stats()

            # 2. 委托窗口深模块追踪
            self._window_tracker.record(model_id, current_min, tokens=total, latency_ms=latency_ms)
            self._prune_windows()

        # 计费估算日志
        model_cfg = self.model_configs.get(model_id)
        if model_cfg:
            i_cost = (input_tokens / 1000) * model_cfg.input_cost_1k
            o_cost = (output_tokens / 1000) * model_cfg.output_cost_1k
            total_cost = i_cost + o_cost
            rpd = self.stats.daily_requests[model_id]
            rpm = self._window_tracker.get_rpm(model_id, current_min)
            logger.info(
                f"用量流水: {model_id} | Input:{input_tokens} | Output:{output_tokens} | "
                f"Total:{total} | RPD:{rpd} | RPM:{rpm} | 计费: ${total_cost:.4f}"
            )

    def check_limit(self, model_id: str):
        """委托健康治理器检查限额与黑名单状态。

        锁内执行: governor 会改写共享 blacklist_expiry (check-then-pop)
        并回调 _save_stats 迭代 stats, 必须与其它写路径互斥。
        """
        with self._lock:
            current_min = self._get_current_minute()
            daily_usage = self.stats.daily_usage.get(model_id, 0)
            daily_requests = self.stats.daily_requests.get(model_id, 0)
            rpm = self._window_tracker.get_rpm(model_id, current_min)
            tpm = self._window_tracker.get_tpm(model_id, current_min)

            return self._governor.check_limit(
                model_id=model_id,
                daily_usage=daily_usage,
                daily_requests=daily_requests,
                current_rpm=rpm,
                current_tpm=tpm,
                on_persist=self._save_stats,
            )

    def check_role_budget(self, role: str, input_tokens: int, output_tokens: int):
        """角色级预算拦截：防止单智能体 Token 异常膨胀（上限为基准的 2 倍）"""
        role_cfg = self.role_configs.get(role)
        if not role_cfg:
            return True, ""
        if input_tokens > role_cfg.max_input_tokens * 2:
            return False, f"角色 [{role}] 输入 Token ({input_tokens}) 严重超限 (上限 {role_cfg.max_input_tokens * 2})"
        if output_tokens > role_cfg.max_output_tokens * 2:
            return False, f"角色 [{role}] 输出 Token ({output_tokens}) 严重超限 (上限 {role_cfg.max_output_tokens * 2})"
        return True, ""

    def get_role_config(self, role: str) -> Optional[RoleConfigV2]:
        return self.role_configs.get(role)

    def blacklist_model(self, model_id: str, reason: str, permanent: bool = False):
        """委托熔断治理器执行黑名单拦截 (锁内: 改写共享黑名单并持久化)"""
        with self._lock:
            self._governor.blacklist_model(model_id, reason, permanent, on_persist=self._save_stats)

    def should_run_startup_probe(self) -> bool:
        """检查今日是否已经执行过全量自检 (check-then-act 在锁内完成)"""
        with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.stats.last_probe_date != today_str:
                self.stats.last_probe_date = today_str
                self._save_stats()
                return True
            return False

    def get_stability_score(self, model_id: str) -> float:
        return self._governor.get_stability_score(model_id)

    def get_avg_latency(self, model_id: str) -> float:
        return self._window_tracker.get_avg_latency(model_id)

    def record_failure(self, model_id: str, error_code: str):
        """记录故障并委托健康治理器惩罚健康分或物理熔断。

        锁内执行: 健康分扣减是 read → -0.2 → write 的非原子序列,
        绕过锁的并发扣分会丢更新, 导致熔断该触发时不触发。
        """
        with self._lock:
            self._governor.record_failure(model_id, error_code, on_persist=self._save_stats)

    def record_success(self, model_id: str):
        """成功后回弹健康分并自愈清除黑名单 (锁内: 与故障扣分路径互斥)"""
        with self._lock:
            self._governor.record_success(model_id, on_persist=self._save_stats)

    def reset_blacklists(self):
        """强制重置全量黑名单 (锁内: clear 共享 dict 不得与 _save_stats 的迭代并发)"""
        with self._lock:
            self._governor.reset_blacklists(on_persist=self._save_stats)

    def get_usage_report(self) -> str:
        """生成今日算力消耗报告 (锁内取共享 dict 快照, 迭代在锁外)"""
        with self._lock:
            daily_usage = dict(self.stats.daily_usage)
            daily_requests = dict(self.stats.daily_requests)
        report = ["\n--- 今日算力消耗报告 ---"]
        for m_id, tokens in daily_usage.items():
            reqs = daily_requests.get(m_id, 0)
            report.append(f"- {m_id}: {tokens} tokens | {reqs} requests")
        return "\n".join(report)

    @staticmethod
    def infer_provider(model_id: str) -> str:
        """根据模型 ID 推断供应商名称"""
        mid = model_id.lower()
        if any(k in mid for k in ["qwen", "bailian", "aliyun", "dashscope"]):
            return "阿里云百炼"
        if any(k in mid for k in ["doubao", "volcano", "ark", "ep-", "volc"]):
            return "火山引擎"
        if "deepseek" in mid:
            return "DeepSeek"
        if any(k in mid for k in ["gpt", "azure", "openai"]):
            return "Azure/OpenAI"
        if any(k in mid for k in ["gemini", "google"]):
            return "Google"
        if any(k in mid for k in ["claude", "anthropic"]):
            return "Anthropic"
        return "Unknown"

    def get_governance_snapshot(self) -> Dict[str, Any]:
        """实时算力消耗与治理快照数据"""
        nodes = []
        total_tokens = 0
        total_cost = 0.0

        # 锁内取共享 dict 快照, 重计算在锁外; 避免迭代期间被写路径并发改写
        with self._lock:
            usage_snapshot = dict(self.stats.daily_usage)
            requests_snapshot = dict(self.stats.daily_requests)
            total_snapshot = dict(self.stats.total_usage)
            blacklist_snapshot = dict(self.stats.blacklist_expiry)

        for model_id, cfg in self.model_configs.items():
            daily_tokens = usage_snapshot.get(model_id, 0)
            daily_requests = requests_snapshot.get(model_id, 0)
            total_tokens_all = total_snapshot.get(model_id, 0)
            stability = self.get_stability_score(model_id)
            avg_latency = self.get_avg_latency(model_id)

            i_tokens = int(daily_tokens * 0.6)
            o_tokens = daily_tokens - i_tokens
            cost = (i_tokens / 1000) * cfg.input_cost_1k + (o_tokens / 1000) * cfg.output_cost_1k

            is_blacklisted = not cfg.is_active or (
                model_id in blacklist_snapshot and time.time() < blacklist_snapshot.get(model_id, 0)
            )
            status = "BLACKLISTED" if is_blacklisted else ("ACTIVE" if daily_requests > 0 else "STANDBY")

            nodes.append({
                "id": model_id,
                "provider": self.infer_provider(model_id),
                "tier": cfg.priority if hasattr(cfg, "priority") else 1,
                "status": status,
                "daily_tokens": daily_tokens,
                "daily_requests": daily_requests,
                "total_tokens": total_tokens_all,
                "daily_quota": cfg.daily_quota,
                "quota_pct": round(daily_tokens / cfg.daily_quota * 100, 1) if cfg.daily_quota else 0,
                "cost_usd": round(cost, 4),
                "stability": round(stability * 100),
                "avg_latency_ms": round(avg_latency),
                "burnout_rounds": self.get_burnout_prediction(model_id),
                "last_error": cfg.last_error,
            })
            total_tokens += daily_tokens
            total_cost += cost

        nodes.sort(key=lambda x: x["daily_tokens"], reverse=True)

        return {
            "timestamp": datetime.now().isoformat(),
            "today": self.stats.today,
            "total_daily_tokens": total_tokens,
            "total_daily_cost_usd": round(total_cost, 4),
            "active_nodes": sum(1 for n in nodes if n["status"] == "ACTIVE"),
            "blacklisted_nodes": sum(1 for n in nodes if n["status"] == "BLACKLISTED"),
            "nodes": nodes,
        }

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """实时 Token 消耗与成本细分指标"""
        # 锁内取共享 dict 快照, 避免末尾 sum(values()) 迭代期间被写路径并发改写
        with self._lock:
            daily = dict(self.stats.daily_usage)
            total = dict(self.stats.total_usage)
            requests_snapshot = dict(self.stats.daily_requests)
        current_min = self._get_current_minute()

        models_detail = []
        for model_id, cfg in self.model_configs.items():
            current = daily.get(model_id, 0)
            rpd = self.stats.daily_requests.get(model_id, 0)
            rpm = self._window_tracker.get_rpm(model_id, current_min)
            tpm = self._window_tracker.get_tpm(model_id, current_min)

            quota = cfg.daily_quota
            i_cost_rate = cfg.input_cost_1k
            o_cost_rate = cfg.output_cost_1k
            est_cost = (current / 1000) * (i_cost_rate * 0.75 + o_cost_rate * 0.25)

            models_detail.append({
                "id": model_id,
                "name": cfg.model_name,
                "provider": cfg.provider,
                "daily_used": current,
                "daily_quota": quota,
                "daily_requests": rpd,
                "rpd_limit": cfg.rpd_limit,
                "current_rpm": rpm,
                "rpm_limit": cfg.rpm_limit,
                "current_tpm": tpm,
                "tpm_limit": cfg.tpm_limit,
                "usage_pct": round(current / max(quota, 1) * 100, 1),
                "estimated_cost": round(est_cost, 4),
                "lifetime_tokens": total.get(model_id, 0),
                "remaining_tokens": self.cloud_remaining_tokens.get(model_id),
            })

        return {
            "date": self.stats.today,
            "current_minute": current_min,
            "models": models_detail,
            "total_daily_tokens": sum(daily.values()),
            "total_lifetime_tokens": sum(total.values()),
            "total_daily_requests": sum(requests_snapshot.values()),
        }


# 模块级单例代理 (通过 DI 容器延迟加载)
from app.core.container import LazyProxy

usage_tracker = LazyProxy("usage_tracker")
