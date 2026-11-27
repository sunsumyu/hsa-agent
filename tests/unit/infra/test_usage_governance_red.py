"""
tests/unit/infra/test_usage_governance_red.py
=============================================
Red unit tests for UsageTracker governance snapshot, provider detection,
and realtime metrics aggregation (Deep Module).
"""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock

from app.core.schemas import ModelConfig, UsageStats
from app.infra.usage_tracker import UsageTracker


@pytest.fixture
def test_tracker(tmp_path: Path):
    stats_file = tmp_path / "test_stats.json"
    tracker = UsageTracker(
        stats_path=str(stats_file),
        config_path="non_existent.json",
        role_path="non_existent.json"
    )

    # Inject mock model configs
    cfg_qwen = ModelConfig(
        id="qwen-plus-01",
        provider="aliyun",
        model_name="qwen-plus",
        family="qwen",
        platform="dashscope",
        api_key_env="DASHSCOPE_API_KEY",
        daily_quota=100000,
        input_cost_1k=0.004,
        output_cost_1k=0.012,
        is_active=True
    )
    cfg_deepseek = ModelConfig(
        id="deepseek-chat-01",
        provider="deepseek",
        model_name="deepseek-chat",
        family="deepseek",
        platform="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        daily_quota=50000,
        input_cost_1k=0.001,
        output_cost_1k=0.002,
        is_active=True
    )

    tracker.model_configs = {
        "qwen-plus-01": cfg_qwen,
        "deepseek-chat-01": cfg_deepseek,
    }

    # Populate usage stats
    tracker.stats.daily_usage = {
        "qwen-plus-01": 10000,
        "deepseek-chat-01": 5000,
    }
    tracker.stats.daily_requests = {
        "qwen-plus-01": 25,
        "deepseek-chat-01": 10,
    }
    tracker.stats.total_usage = {
        "qwen-plus-01": 50000,
        "deepseek-chat-01": 20000,
    }
    tracker.stability_scores = {
        "qwen-plus-01": 0.95,
        "deepseek-chat-01": 0.80,
    }

    return tracker


def test_infer_provider():
    assert UsageTracker.infer_provider("qwen-max-latest") == "阿里云百炼"
    assert UsageTracker.infer_provider("doubao-pro-32k") == "火山引擎"
    assert UsageTracker.infer_provider("deepseek-v3") == "DeepSeek"
    assert UsageTracker.infer_provider("gpt-4o-mini") == "Azure/OpenAI"
    assert UsageTracker.infer_provider("gemini-1.5-flash") == "Google"
    assert UsageTracker.infer_provider("claude-3-5-sonnet") == "Anthropic"
    assert UsageTracker.infer_provider("random-custom-model") == "Unknown"


def test_get_governance_snapshot(test_tracker: UsageTracker):
    snapshot = test_tracker.get_governance_snapshot()

    assert "timestamp" in snapshot
    assert "today" in snapshot
    assert snapshot["total_daily_tokens"] == 15000
    assert snapshot["active_nodes"] == 2
    assert snapshot["blacklisted_nodes"] == 0
    assert len(snapshot["nodes"]) == 2

    # Sorted by daily_tokens descending
    top_node = snapshot["nodes"][0]
    assert top_node["id"] == "qwen-plus-01"
    assert top_node["daily_tokens"] == 10000
    assert top_node["daily_requests"] == 25
    assert top_node["quota_pct"] == 10.0
    assert top_node["cost_usd"] > 0
    assert top_node["stability"] == 95
    assert top_node["status"] == "ACTIVE"


def test_get_realtime_metrics(test_tracker: UsageTracker):
    metrics = test_tracker.get_realtime_metrics()

    assert "date" in metrics
    assert "current_minute" in metrics
    assert metrics["total_daily_tokens"] == 15000
    assert metrics["total_daily_requests"] == 35
    assert len(metrics["models"]) == 2

    qwen_metric = next(m for m in metrics["models"] if m["id"] == "qwen-plus-01")
    assert qwen_metric["daily_used"] == 10000
    assert qwen_metric["daily_quota"] == 100000
    assert qwen_metric["usage_pct"] == 10.0
    assert qwen_metric["estimated_cost"] > 0
