import pytest
from unittest.mock import MagicMock, patch
from fastapi import BackgroundTasks, Request
from app.api.chat_stream_coordinator import ChatStreamCoordinator
from contextlib import contextmanager

@pytest.mark.asyncio
async def test_coordinate_stream_blocks_concurrent_same_session():
    """验证当相同 session_id 正在进行审计推演（锁冲突）时，必须熔断并下发去重提示，严禁并发执行图节点"""
    coordinator = ChatStreamCoordinator()

    req = MagicMock(spec=Request)
    req.app.state.saver = None
    bg_tasks = MagicMock(spec=BackgroundTasks)

    @contextmanager
    def mock_dist_lock(self, key, timeout=120):
        yield False

    with patch("app.infra.redis_client.RedisClient.dist_lock", mock_dist_lock):
        with patch("app.api.chat_stream_coordinator.get_graph_executor") as mock_executor:
            generator = coordinator.coordinate_stream(
                request=req,
                background_tasks=bg_tasks,
                session_id="session_conflict_123",
                model_id="test_model",
                message="测试重复请求"
            )
            chunks = [chunk async for chunk in generator]

            full_text = "".join(chunks)
            assert "请勿重复提交" in full_text
            assert "已有审计推演正在进行中" in full_text
            # 必须严禁进入图推演
            assert mock_executor.called is False
