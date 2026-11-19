# tests/unit/core/observability/test_adaptive_sampler.py
import pytest
from unittest.mock import patch
from app.core.observability.adaptive_sampler import AdaptiveSampler

def test_should_sample_always_on_error():
    sampler = AdaptiveSampler(sample_rate=0.0) # 即使基础采样率为0
    assert sampler.should_sample(has_error=True, duration_seconds=0.1, tags=[]) is True

def test_should_sample_always_on_slow_request():
    sampler = AdaptiveSampler(sample_rate=0.0, slow_threshold=5.0)
    assert sampler.should_sample(has_error=False, duration_seconds=5.5, tags=[]) is True

def test_should_sample_always_on_hitl():
    sampler = AdaptiveSampler(sample_rate=0.0)
    assert sampler.should_sample(has_error=False, duration_seconds=0.1, tags=["hitl-gate"]) is True

def test_should_sample_obeys_sample_rate():
    with patch("random.random", return_value=0.03):
        sampler = AdaptiveSampler(sample_rate=0.05)
        assert sampler.should_sample(has_error=False, duration_seconds=1.0, tags=[]) is True

    with patch("random.random", return_value=0.08):
        sampler = AdaptiveSampler(sample_rate=0.05)
        assert sampler.should_sample(has_error=False, duration_seconds=1.0, tags=[]) is False

def test_network_reachability_probe():
    sampler = AdaptiveSampler()
    # 模拟探测成功（清理环境代理干扰）
    with patch.dict("os.environ", {"HTTPS_PROXY": "", "https_proxy": "", "ALL_PROXY": ""}, clear=True):
        with patch("socket.create_connection") as mock_conn:
            assert sampler.is_network_reachable("https://api.smith.langchain.com") is True
        # 模拟探测失败触发熔断
        with patch("socket.create_connection", side_effect=OSError("Timeout")):
            assert sampler.is_network_reachable("https://unreachable.smith.com") is False
