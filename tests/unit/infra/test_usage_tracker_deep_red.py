"""
tests/unit/infra/test_usage_tracker_deep_red.py
==============================================
Matt Pocock 风格契约测试：
验证滑动窗口追踪器 UsageWindowTracker、健康熔断治理器 ModelHealthGovernor，
以及组合门面 UsageTracker 的深模块协作与向后兼容性。
"""

import pytest
import time
from pathlib import Path
from datetime import datetime, timedelta

from app.core.schemas import ModelConfig, UsageStats, RoleConfigV2
from app.infra.usage_window_tracker import UsageWindowTracker
from app.infra.model_health_governor import ModelHealthGovernor
from app.infra.usage_tracker import UsageTracker


class TestUsageTrackerDeepModules:
    def test_usage_window_tracker_aggregation_and_prune(self):
        tracker = UsageWindowTracker()
        m1 = "qwen-plus"
        min1 = "2026-10-19 10:00"
        min2 = "2026-10-19 10:01"

        # 记录 min1
        tracker.record(m1, min1, tokens=500, latency_ms=120.0)
        tracker.record(m1, min1, tokens=300, latency_ms=80.0)

        assert tracker.get_rpm(m1, min1) == 2
        assert tracker.get_tpm(m1, min1) == 800
        assert tracker.get_avg_latency(m1) == 100.0

        # 记录 min2
        tracker.record(m1, min2, tokens=1000, latency_ms=200.0)
        assert tracker.get_rpm(m1, min2) == 1
        assert tracker.get_tpm(m1, min2) == 1000

        # 滑动窗口修剪（只保留 min2）
        tracker.prune(current_minute=min2)
        assert tracker.get_rpm(m1, min1) == 0
        assert tracker.get_rpm(m1, min2) == 1

    def test_model_health_governor_blacklist_and_recovery(self):
        configs = {
            "m1": ModelConfig(
                id="m1",
                provider="test",
                model_name="m1",
                family="test",
                platform="test",
                api_key_env="TEST_KEY",
                daily_quota=10000,
                rpm_limit=10,
                tpm_limit=5000,
                is_active=True,
            )
        }
        blacklist_expiry = {}
        stability_scores = {}

        gov = ModelHealthGovernor(
            model_configs=configs,
            blacklist_expiry=blacklist_expiry,
            stability_scores=stability_scores,
        )

        # 1. 触发 403 物理熔断
        gov.record_failure("m1", error_code="HTTP 403 Forbidden: Account suspended")
        assert configs["m1"].is_active is False
        assert gov.get_stability_score("m1") == 0.0
        assert "m1" in blacklist_expiry
        # 熔断时间应在今日 23:59:59 附近
        now = datetime.now()
        eod = datetime(now.year, now.month, now.day) + timedelta(days=1)
        assert abs(blacklist_expiry["m1"] - eod.timestamp()) < 60

        # 2. 检查限制拦截
        allowed, _, _, reason = gov.check_limit("m1", daily_usage=0, daily_requests=0, current_rpm=0, current_tpm=0)
        assert allowed is False
        assert "临时拉黑中" in reason or "封禁" in reason

        # 3. 记录成功触发自愈
        gov.record_success("m1")
        assert configs["m1"].is_active is True
        assert "m1" not in blacklist_expiry
        assert gov.get_stability_score("m1") > 0.0

        # 4. 404 永久失效
        gov.record_failure("m1", error_code="404 Not Found: model_not_found")
        assert configs["m1"].is_active is False
        assert "模型不存在" in configs["m1"].last_error or "404" in configs["m1"].last_error

    def test_usage_tracker_facade_composition(self, tmp_path: Path):
        stats_file = tmp_path / "stats.json"
        tracker = UsageTracker(
            stats_path=str(stats_file),
            config_path="non_existent.json",
            role_path="non_existent.json",
        )

        cfg = ModelConfig(
            id="test-model",
            provider="test",
            model_name="test-model",
            family="test",
            platform="test",
            api_key_env="TEST_KEY",
            daily_quota=5000,
            rpm_limit=5,
            tpm_limit=2000,
            is_active=True,
        )
        tracker.model_configs = {"test-model": cfg}

        # 记录调用
        tracker.record_usage(
            model_id="test-model",
            input_tokens=100,
            output_tokens=200,
            latency_ms=150.0,
        )

        assert tracker.stats.daily_usage["test-model"] == 300
        assert tracker.stats.daily_requests["test-model"] == 1
        assert tracker.get_avg_latency("test-model") == 150.0

        # 角色预算拦截契约
        tracker.role_configs = {
            "planner": RoleConfigV2(
                role="planner",
                model="test-model",
                pool="primary",
                max_input_tokens=1000,
                max_output_tokens=500,
            )
        }
        ok, _ = tracker.check_role_budget("planner", input_tokens=1500, output_tokens=400)
        assert ok is True

        # 超过 2 倍预算拦截
        blocked_in, err_in = tracker.check_role_budget("planner", input_tokens=2500, output_tokens=400)
        assert blocked_in is False
        assert "严重超限" in err_in

        blocked_out, err_out = tracker.check_role_budget("planner", input_tokens=500, output_tokens=1200)
        assert blocked_out is False
        assert "严重超限" in err_out
