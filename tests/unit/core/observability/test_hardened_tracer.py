# tests/unit/core/observability/test_hardened_tracer.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.core.observability.hardened_tracer import HardenedTracer
from app.core.observability.adaptive_sampler import AdaptiveSampler


def test_hardened_tracer_sanitizes_and_persists():
    mock_client = MagicMock()
    sampler = AdaptiveSampler(sample_rate=1.0)
    tracer = HardenedTracer(project_name="test-project", client=mock_client, sampler=sampler)

    # 模拟一个 LangChain Run 对象
    mock_run = MagicMock()
    mock_run.error = None
    mock_run.start_time = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    mock_run.end_time = datetime(2026, 11, 2, 12, 0, 1, tzinfo=timezone.utc)
    mock_run.tags = ["ppio-premium"]
    mock_run.inputs = {"query": "核查身份证 110101199003072345 的就诊明细"}
    mock_run.outputs = {"summary": "联系电话 13800138000 确认违规"}

    with patch.object(HardenedTracer, "_send_to_backend") as mock_send:
        tracer._persist_run(mock_run)
        assert mock_send.called
        # 断言入参和出参已被脱敏
        assert "110101199003072345" not in str(mock_run.inputs)
        assert "13800138000" not in str(mock_run.outputs)


def test_hardened_tracer_drops_unsampled_run():
    mock_client = MagicMock()
    sampler = AdaptiveSampler(sample_rate=0.0)  # 0 采样率且无错误
    tracer = HardenedTracer(project_name="test-project", client=mock_client, sampler=sampler)

    mock_run = MagicMock()
    mock_run.error = None
    mock_run.start_time = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    mock_run.end_time = datetime(2026, 11, 2, 12, 0, 1, tzinfo=timezone.utc)
    mock_run.tags = ["normal"]

    with patch.object(HardenedTracer, "_send_to_backend") as mock_send:
        tracer._persist_run(mock_run)
        assert not mock_send.called  # 未采样的请求直接丢弃，不发生网络调用


def test_hardened_tracer_default_sampler_and_error_sampling():
    # 测试默认初始化 sampler 以及 error 强采样
    mock_client = MagicMock()
    tracer = HardenedTracer(project_name="test-project", client=mock_client)
    assert isinstance(tracer.sampler, AdaptiveSampler)

    mock_run = MagicMock()
    mock_run.error = "RuntimeError: Database timeout"
    mock_run.start_time = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
    mock_run.end_time = datetime(2026, 11, 2, 12, 0, 1, tzinfo=timezone.utc)
    mock_run.tags = []
    mock_run.inputs = {"secret": "supersecretpassword"}
    mock_run.outputs = None

    with patch.object(HardenedTracer, "_send_to_backend") as mock_send:
        tracer._persist_run(mock_run)
        assert mock_send.called
        assert mock_run.inputs["secret"] == "[REDACTED]"


def test_hardened_tracer_send_to_backend_delegates_to_super():
    mock_client = MagicMock()
    tracer = HardenedTracer(project_name="test-project", client=mock_client)
    mock_run = MagicMock()

    with patch("langchain_core.tracers.LangChainTracer._persist_run") as mock_super_persist:
        tracer._send_to_backend(mock_run)
        mock_super_persist.assert_called_once_with(mock_run)
