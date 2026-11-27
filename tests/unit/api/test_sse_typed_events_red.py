"""
tests/unit/api/test_sse_typed_events_red.py
============================================
测试强类型 SSE 协议契约 (SSEEvent) 与内容协商双轨机制。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, BackgroundTasks, Request
from starlette.testclient import TestClient

from app.api.events.sse_contract import SSEEvent, SSEEventType
from app.api.chat_stream_coordinator import ChatStreamCoordinator
from app.api.routes.chat import router as chat_router


def test_sse_event_serialization():
    """验证 SSEEvent 序列化为标准 W3C SSE 格式与历史兼容格式"""
    # 1. 状态事件
    status_evt = SSEEvent(
        event=SSEEventType.STATUS,
        data={"message": "正在处理上一轮审计推演，请勿重复提交...", "in_flight": True}
    )
    sse_text = status_evt.to_sse_packet()
    assert sse_text.startswith("event: status\n")
    assert 'data: {"message": "正在处理上一轮审计推演，请勿重复提交...", "in_flight": true}' in sse_text
    assert sse_text.endswith("\n\n")

    # 兼容格式
    legacy_text = status_evt.to_legacy_packet()
    assert "[[[STATUS: 正在处理上一轮审计推演，请勿重复提交...]]]" in legacy_text

    # 2. 正文事件
    msg_evt = SSEEvent(
        event=SSEEventType.MESSAGE,
        data="⚠️ 当前会话已有推演正在进行中"
    )
    assert msg_evt.to_sse_packet() == "event: message\ndata: ⚠️ 当前会话已有推演正在进行中\n\n"
    assert msg_evt.to_legacy_packet() == "⚠️ 当前会话已有推演正在进行中"

    # 3. 引擎事件
    engine_evt = SSEEvent(event=SSEEventType.ENGINE, data="deepseek-v3")
    assert engine_evt.to_sse_packet() == "event: engine\ndata: deepseek-v3\n\n"
    assert engine_evt.to_legacy_packet() == "[[[ENGINE:deepseek-v3]]]"


@pytest.mark.asyncio
async def test_coordinate_stream_in_flight_lock_sse_mode():
    """验证当触发会话飞行锁拦截时，SSE 模式下发结构化事件帧"""
    coordinator = ChatStreamCoordinator()
    req = MagicMock(spec=Request)
    req.headers = {"accept": "text/event-stream"}
    req.query_params = {}
    bg_tasks = MagicMock(spec=BackgroundTasks)

    from contextlib import contextmanager
    @contextmanager
    def mock_dist_lock(self, key, timeout=120):
        yield False

    with patch("app.infra.redis_client.RedisClient.dist_lock", mock_dist_lock):
        generator = coordinator.coordinate_stream(
            request=req,
            background_tasks=bg_tasks,
            session_id="session_conflict_sse",
            model_id="test_model",
            message="测试重复提交",
            stream_format="sse",
        )
        chunks = [chunk async for chunk in generator]
        full_text = "".join(chunks)

        # 验证输出标准 SSE 格式而非原始字符串
        assert "event: status\n" in full_text
        assert "event: message\n" in full_text
        assert "event: done\n" in full_text
        assert "[[[STATUS:" not in full_text  # 强类型模式下不泄露方括号暗号


@pytest.mark.asyncio
async def test_coordinate_stream_full_flow_sse_mode():
    """验证完整图推演在 SSE 模式下下发的 engine、thought、message 强类型事件流"""
    coordinator = ChatStreamCoordinator()
    mock_executor = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.next = []
    mock_snapshot.values = {}
    mock_executor.aget_state = AsyncMock(return_value=mock_snapshot)

    async def fake_stream_events(*args, **kwargs):
        yield {
            "event": "on_chat_model_stream",
            "name": "model_step",
            "metadata": {"langgraph_node": "PLANNER"},
            "data": {"chunk": MagicMock(content="正在规划审计策略")},
        }
        yield {
            "event": "on_chain_start",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {},
        }
        yield {
            "event": "on_chat_model_stream",
            "name": "reporter_step",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {"chunk": MagicMock(content="交付核查报告正文")},
        }

    mock_executor.astream_events = fake_stream_events

    with patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "deepseek-chat")):
        with patch("app.core.memory.history.HistoryManager.get_history", return_value=[]):
            with patch("app.core.memory.history.HistoryManager.save_turn"):
                with patch("app.core.memory.history.HistoryManager.dump_debug_history"):
                    req = MagicMock(spec=Request)
                    req.headers = {"accept": "text/event-stream"}
                    req.query_params = {}
                    bg = MagicMock(spec=BackgroundTasks)

                    chunks = []
                    async for chunk in coordinator.coordinate_stream(
                        request=req,
                        background_tasks=bg,
                        session_id="test_sse_sess_1",
                        model_id="deepseek-chat",
                        message="排查大额异常",
                        stream_format="sse",
                    ):
                        chunks.append(chunk)

                    full_text = "".join(chunks)
                    # 验证标准 SSE 格式
                    assert "event: engine\ndata: deepseek-chat\n\n" in full_text
                    assert "event: version\ndata: deepseek-chat\n\n" in full_text
                    assert "event: thought\n" in full_text
                    assert "正在规划审计策略" in full_text
                    assert "event: message\n" in full_text
                    assert "交付核查报告正文" in full_text
                    assert "event: done\ndata: [DONE]\n\n" in full_text


def test_http_endpoint_content_negotiation():
    """验证 POST /agent/chat 端点在不同 Accept 头下的自动内容协商"""
    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app, raise_server_exceptions=False)

    payload = {
        "message": "排查大额结算流水",
        "model_id": "deepseek-chat",
        "session_id": "test_negotiation_sess"
    }

    # 1. 携带 Accept: text/event-stream -> 响应 text/event-stream & typed-sse-v2
    with patch("app.api.chat_stream_coordinator.ChatStreamCoordinator.coordinate_stream") as mock_coord:
        async def fake_generator(*args, **kwargs):
            yield "event: message\ndata: test\n\n"
        mock_coord.return_value = fake_generator()

        resp_sse = client.post(
            "/agent/chat",
            json=payload,
            headers={"Accept": "text/event-stream"}
        )
        assert resp_sse.status_code == 200
        assert "text/event-stream" in resp_sse.headers["content-type"]
        assert resp_sse.headers["x-stream-protocol"] == "typed-sse-v2"

    # 2. 携带 Accept: text/plain (或默认无特殊 Accept) -> 响应 text/plain & legacy-inband-v1
    with patch("app.api.chat_stream_coordinator.ChatStreamCoordinator.coordinate_stream") as mock_coord:
        async def fake_generator(*args, **kwargs):
            yield "[[[ENGINE:deepseek-chat]]] test"
        mock_coord.return_value = fake_generator()

        resp_legacy = client.post(
            "/agent/chat",
            json=payload,
            headers={"Accept": "text/plain"}
        )
        assert resp_legacy.status_code == 200
        assert "text/plain" in resp_legacy.headers["content-type"]
        assert resp_legacy.headers["x-stream-protocol"] == "legacy-inband-v1"
