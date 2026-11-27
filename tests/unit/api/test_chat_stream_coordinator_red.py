import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, BackgroundTasks, Request
from starlette.testclient import TestClient
from app.api.chat_stream_coordinator import ChatStreamCoordinator, chat_stream_coordinator
from app.api.routes.chat import router as chat_router


@pytest.fixture
def mock_app_state():
    app = FastAPI()
    app.state.saver = None
    app.include_router(chat_router)
    return app


@pytest.mark.asyncio
async def test_chat_stream_coordinator_yields_engine_headers_and_events():
    coordinator = ChatStreamCoordinator()

    # 模拟图执行器
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
            "data": {"chunk": MagicMock(content="分析报告规划中")},
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
            "data": {"chunk": MagicMock(content="最终核查交付报告")},
        }

    mock_executor.astream_events = fake_stream_events

    with patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "deepseek-chat")):
        with patch("app.core.memory.history.HistoryManager.get_history", return_value=[]):
            with patch("app.core.memory.history.HistoryManager.save_turn") as mock_save:
                with patch("app.core.memory.history.HistoryManager.dump_debug_history") as mock_dump:
                    mock_request = MagicMock(spec=Request)
                    mock_request.app.state.saver = None
                    mock_bg = MagicMock(spec=BackgroundTasks)

                    chunks = []
                    async for chunk in coordinator.coordinate_stream(
                        request=mock_request,
                        background_tasks=mock_bg,
                        session_id="test_sess_01",
                        model_id="deepseek-chat",
                        message="排查大额结算",
                    ):
                        chunks.append(chunk)

                    full_text = "".join(chunks)
                    # 验证物理引擎首包
                    assert "[[[ENGINE:deepseek-chat]]]" in full_text
                    assert "[[[VERSION:deepseek-chat]]]" in full_text
                    # 验证推演思考容器与交付内容
                    assert ":::thought" in full_text
                    assert "最终核查交付报告" in full_text
                    # 验证历史持久化被调用
                    mock_save.assert_called_once()
                    mock_dump.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream_coordinator_exception_handling():
    coordinator = ChatStreamCoordinator()

    mock_executor = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.next = []
    mock_executor.aget_state = AsyncMock(return_value=mock_snapshot)

    async def broken_stream_events(*args, **kwargs):
        raise RuntimeError("LLM Connection Refused 502")
        yield {}

    mock_executor.astream_events = broken_stream_events

    with patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "qwen-max")):
        with patch("app.core.memory.history.HistoryManager.get_history", return_value=[]):
            with patch("app.core.memory.history.HistoryManager.save_turn") as mock_save:
                with patch("app.infra.usage_tracker.UsageTracker.record_failure") as mock_fail:
                    mock_request = MagicMock(spec=Request)
                    mock_request.app.state.saver = None
                    mock_bg = MagicMock(spec=BackgroundTasks)

                    chunks = []
                    async for chunk in coordinator.coordinate_stream(
                        request=mock_request,
                        background_tasks=mock_bg,
                        session_id="test_sess_err",
                        model_id="qwen-max",
                        message="查询",
                    ):
                        chunks.append(chunk)

                    full_text = "".join(chunks)
                    assert len(chunks) > 0
                    mock_fail.assert_called_once()
                    mock_save.assert_called_once()


def test_chat_route_endpoint(mock_app_state):
    client = TestClient(mock_app_state)

    async def dummy_gen(*args, **kwargs):
        yield "[[[ENGINE:mock-engine]]]"
        yield "Hello Stream"

    with patch.object(chat_stream_coordinator, "coordinate_stream", side_effect=dummy_gen):
        resp = client.post(
            "/agent/chat",
            json={"message": "你好", "session_id": "test_s1"},
        )
        assert resp.status_code == 200
        assert "Hello Stream" in resp.text
        assert resp.headers["cache-control"] == "no-cache, no-store, must-revalidate"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_format", ["legacy", "sse"])
async def test_reporter_raw_stream_is_buffered_and_final_guarded_report_is_delivered(stream_format):
    coordinator = ChatStreamCoordinator()
    raw_draft = (
        "初步核查认为本案违反《虚假医保特别法》第九十九条及医保发〔2023〕X号，需要退回全部违规资金并处五倍罚款。"
    )
    guarded_report = (
        "# 📋 医保专项稽核报告\n\n## 四、核查结论\n\n[已拦截未核验法规引用]\n\n"
        "## 六、证据链溯源明细\n| Citation ID | 来源类型 |"
    )

    mock_executor = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.next = []
    mock_snapshot.values = {}
    mock_executor.aget_state = AsyncMock(return_value=mock_snapshot)

    async def fake_stream_events(*args, **kwargs):
        yield {
            "event": "on_chain_start",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {},
        }
        yield {
            "event": "on_chat_model_stream",
            "name": "reporter_llm",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {"chunk": MagicMock(content=raw_draft)},
        }
        yield {
            "event": "on_chain_end",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {"output": {"messages": [MagicMock(content=guarded_report)]}},
        }

    mock_executor.astream_events = fake_stream_events
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.saver = None
    mock_request.headers = {}
    mock_request.query_params = {}
    mock_bg = MagicMock(spec=BackgroundTasks)

    with (
        patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "qwen-max")),
        patch("app.core.memory.history.HistoryManager.get_history", return_value=[]),
        patch("app.core.memory.history.HistoryManager.save_turn") as mock_save,
        patch("app.core.memory.history.HistoryManager.dump_debug_history"),
    ):
        chunks = [
            c
            async for c in coordinator.coordinate_stream(
                request=mock_request,
                background_tasks=mock_bg,
                session_id=f"sess_guard_{stream_format}",
                model_id="qwen-max",
                message="排查分解住院",
                stream_format=stream_format,
            )
        ]

    full_output = "".join(chunks)
    assert "虚假医保特别法" not in full_output
    assert "## 六、证据链溯源明细" in full_output
    assert "[已拦截未核验法规引用]" in full_output
    persisted = mock_save.call_args.args[2]
    assert "虚假医保特别法" not in persisted
    assert "## 六、证据链溯源明细" in persisted
