import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.infra.endpoint_ping_probe import EndpointPingProbe
from app.infra.endpoint_healing_coordinator import EndpointHealingCoordinator
from app.infra.endpoint_prober import EndpointProber


@pytest.mark.asyncio
async def test_endpoint_ping_probe_missing_key():
    """测试当缺少 API Key 时安全返回 False"""
    mock_ep = MagicMock()
    mock_ep.provider = "openai"
    mock_factory = MagicMock()
    mock_factory.resolve_credentials.return_value = (None, None)

    probe = EndpointPingProbe(factory=mock_factory)
    result = await probe.ping_endpoint("test-ep-1", mock_ep)
    assert result is False


@pytest.mark.asyncio
async def test_endpoint_ping_probe_openai_success():
    """测试 OpenAI Provider 构造并发送 ping 请求成功"""
    mock_ep = MagicMock()
    mock_ep.provider = "openai"
    mock_ep.model_name = "gpt-4o"
    mock_factory = MagicMock()
    mock_factory.resolve_credentials.return_value = ("sk-test-key", "https://api.openai.com/v1")

    probe = EndpointPingProbe(factory=mock_factory)
    mock_chat = AsyncMock()
    mock_chat.ainvoke.return_value = MagicMock(content="pong")

    with patch("langchain_openai.ChatOpenAI", return_value=mock_chat):
        result = await probe.ping_endpoint("test-ep-1", mock_ep)
        assert result is True
        mock_chat.ainvoke.assert_awaited_once()


def test_endpoint_healing_coordinator_detection_and_heal():
    """测试自愈协调器冷却状态检测与自愈恢复"""
    coordinator = EndpointHealingCoordinator()

    mock_pool_mgr = MagicMock()
    mock_state = MagicMock()
    mock_state.is_cooling = True
    mock_pool_mgr.states = {"ep-1": mock_state}

    mock_tracker = MagicMock()
    mock_tracker.blacklist_expiry = {"ep-1": 100000.0}

    mock_redis = MagicMock()

    # 检测节点是否处于需要自愈探测的状态
    needs_probe = coordinator.is_node_cooling_or_blacklisted("ep-1", pool_manager=mock_pool_mgr, tracker=mock_tracker)
    assert needs_probe is True

    # 触发节点自愈恢复
    coordinator.heal_node("ep-1", pool_manager=mock_pool_mgr, tracker=mock_tracker)
    mock_pool_mgr.record_success.assert_called_once_with("ep-1")
    mock_tracker.record_success.assert_called_once_with("ep-1")

    # 同步状态至 Redis (非冷却且非黑名单为 True)
    mock_state.is_cooling = False
    mock_tracker.blacklist_expiry.clear()
    coordinator.sync_node_health_to_redis("ep-1", pool_manager=mock_pool_mgr, tracker=mock_tracker, redis_client=mock_redis)
    mock_redis.record_node_health.assert_called_once_with("ep-1", True)


@pytest.mark.asyncio
async def test_endpoint_prober_facade_integration():
    """测试 EndpointProber 门面协同探测与巡检流程"""
    prober = EndpointProber()
    assert hasattr(prober, "probe_all_endpoints")
    assert hasattr(prober, "_probe_single_endpoint")
    assert hasattr(prober, "run_health_check")
