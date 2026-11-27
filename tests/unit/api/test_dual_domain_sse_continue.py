"""
tests/unit/api/test_dual_domain_sse_continue.py
================================================
Offline unit tests verifying typed W3C SSE parity for LegalStreamCoordinator,
explicit audit routing guard in ChatStreamCoordinator, and HTTP SSE round-trip.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI, Request
from starlette.testclient import TestClient

import app.api.legal_stream_coordinator as lsc_mod
from app.api.chat_stream_coordinator import ChatStreamCoordinator, _is_legal_request
from app.api.legal_stream_coordinator import LegalStreamCoordinator
from app.api.routes.chat import router as chat_router
from app.core.memory.history import HistoryManager
from app.core.memory.session_store import SessionStore


def test_is_legal_request_respects_explicit_audit_model_id():
    msg = "核查医院采购合同违约金与货款结算异常情况"
    assert _is_legal_request("audit-agent", msg) is False
    assert _is_legal_request("AUDIT", msg) is False
    assert _is_legal_request("legal-agent", "排查骨水泥重复收费") is True
    assert _is_legal_request(None, msg) is True


@pytest.mark.asyncio
async def test_legal_stream_direct_mode_emits_typed_sse_and_title(tmp_path):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))
    coord = LegalStreamCoordinator()
    fake_areview = AsyncMock(return_value=("【审查意见】违约金上限需按 LPR 校准。", {"prompt": 18, "completion": 42}))
    bg_tasks = MagicMock(spec=BackgroundTasks)

    with (
        patch.object(lsc_mod.contract_reviewer, "areview", new=fake_areview),
        patch.object(lsc_mod, "history_manager", history_mgr),
        patch.object(lsc_mod, "session_store", store),
    ):
        chunks = [
            pkt
            async for pkt in coord.coordinate_legal_stream(
                session_id="legal-sse-direct-1",
                message="【模式：合同审查】请审核采购合同违约金条款。",
                background_tasks=bg_tasks,
                is_sse=True,
            )
        ]

    full_text = "".join(chunks)
    assert "event: engine\ndata: Argus-Legal-Agent\n\n" in full_text
    assert "event: version\ndata: Argus-Legal-v2.0\n\n" in full_text
    assert "event: status\n" in full_text
    assert "event: message\ndata: 【审查意见】违约金上限需按 LPR 校准。\n\n" in full_text
    assert "event: resource\n" in full_text
    assert "event: session_title\n" in full_text
    assert "event: done\ndata: [DONE]\n\n" in full_text
    assert "[[[" not in full_text
    assert len(history_mgr.get_history("legal-sse-direct-1")) == 2
    bg_tasks.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_legal_stream_dialectic_and_inflight_lock_sse_mode(tmp_path):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))
    coord = LegalStreamCoordinator()

    async def fake_graph_astream(*args, **kwargs):
        yield {"ALIGNER": {"case_facts": [{"narrative": "2024年签署借条"}], "evidence_items": []}}
        yield {"REPORTER": {"final_disposition": "法官心证：支持本金及合法利息。"}}

    coord._graph = MagicMock()
    coord._graph.aget_state = AsyncMock(return_value=MagicMock(next=[], values={}))
    coord._graph.astream = fake_graph_astream

    with (
        patch.object(lsc_mod, "history_manager", history_mgr),
        patch.object(lsc_mod, "session_store", store),
    ):
        chunks = [
            pkt
            async for pkt in coord.coordinate_legal_stream(
                session_id="legal-sse-dialectic-1",
                message="借款人欠款 10 万元逾期未还如何主张？",
                is_sse=True,
            )
        ]

    full_text = "".join(chunks)
    assert "event: message\n" in full_text
    assert "法官心证：支持本金及合法利息。" in full_text
    assert "event: session_title\n" in full_text
    assert "event: done\ndata: [DONE]\n\n" in full_text
    assert "[[[" not in full_text

    @contextmanager
    def locked_out(self, key, timeout=120):
        yield False

    with patch("app.infra.redis_client.RedisClient.dist_lock", locked_out):
        locked_chunks = [
            pkt
            async for pkt in coord.coordinate_legal_stream(
                session_id="legal-sse-locked",
                message="测试并发拦截",
                is_sse=True,
            )
        ]
    locked_text = "".join(locked_chunks)
    assert "event: status\n" in locked_text
    assert '"in_flight": true' in locked_text
    assert "event: message\n" in locked_text
    assert "event: done\ndata: [DONE]\n\n" in locked_text


@pytest.mark.asyncio
async def test_chat_coordinator_routes_audit_and_legal_with_sse():
    coord = ChatStreamCoordinator()
    mock_executor = MagicMock()
    mock_snapshot = MagicMock(next=[], values={})
    mock_executor.aget_state = AsyncMock(return_value=mock_snapshot)

    async def fake_stream_events(*args, **kwargs):
        yield {
            "event": "on_chain_start",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {},
        }
        yield {
            "event": "on_chain_end",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {"output": {"messages": [MagicMock(content="审计复核结论：未发现跨科分解住院。")]}},
        }

    mock_executor.astream_events = fake_stream_events

    req = MagicMock(spec=Request)
    req.headers = {"accept": "text/event-stream"}
    req.query_params = {"format": "sse"}
    bg = MagicMock(spec=BackgroundTasks)

    with (
        patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "default")) as mock_exec,
        patch("app.core.memory.history.HistoryManager.get_history", return_value=[]),
        patch("app.core.memory.history.HistoryManager.save_turn"),
        patch("app.core.memory.history.HistoryManager.dump_debug_history"),
        patch("app.api.chat_stream_coordinator.session_store.record_turn", return_value={"title": "审计复核", "title_source": "fallback"}),
    ):
        audit_chunks = [
            pkt
            async for pkt in coord.coordinate_stream(
                request=req,
                background_tasks=bg,
                session_id="audit-guard-1",
                model_id="audit-agent",
                message="核查骨科合同违约金与高值耗材结算问题",
                stream_format="sse",
            )
        ]

    mock_exec.assert_called_once()
    assert mock_exec.call_args.kwargs.get("model_id") is None
    audit_text = "".join(audit_chunks)
    assert "审计复核结论：未发现跨科分解住院。" in audit_text
    assert "event: session_title\n" in audit_text
    assert "event: done\ndata: [DONE]\n\n" in audit_text

    async def fake_legal_stream(**kwargs):
        assert kwargs.get("is_sse") is True
        yield "event: message\ndata: 法律续聊响应\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    with patch("app.api.legal_stream_coordinator.legal_stream_coordinator.coordinate_legal_stream", side_effect=fake_legal_stream):
        legal_chunks = [
            pkt
            async for pkt in coord.coordinate_stream(
                request=req,
                background_tasks=bg,
                session_id="legal-delegate-1",
                model_id="legal-agent",
                message="继续分析借条时效",
                stream_format="sse",
            )
        ]
    assert "".join(legal_chunks) == "event: message\ndata: 法律续聊响应\n\nevent: done\ndata: [DONE]\n\n"


def test_http_legal_sse_roundtrip():
    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app, raise_server_exceptions=False)

    async def fake_legal_gen(**kwargs):
        assert kwargs.get("is_sse") is True
        yield "event: engine\ndata: Argus-Legal-Agent\n\n"
        yield "event: message\ndata: 法律流式测试正文\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    with patch("app.api.legal_stream_coordinator.legal_stream_coordinator.coordinate_legal_stream", side_effect=fake_legal_gen):
        resp = client.post(
            "/agent/chat?format=sse",
            json={"message": "核对借款合同利息", "model_id": "legal-agent", "session_id": "legal-http-1"},
            headers={"Accept": "text/event-stream", "X-Session-Id": "legal-http-1"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert resp.headers["x-stream-protocol"] == "typed-sse-v2"
    assert "event: message\ndata: 法律流式测试正文\n\n" in resp.text
