"""
tests/unit/memory/test_session_management.py
============================================
Offline unit tests for multi-session management, 3-stage title pipeline
(T0 fallback -> T1 async LLM refinement -> T2 manual lock), SSE event, and REST API.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI, Request
from starlette.testclient import TestClient

from app.api.chat_stream_coordinator import ChatStreamCoordinator
from app.api.envelope import register_api_exception_handlers
from app.api.events.sse_contract import SSEEvent, SSEEventType
from app.api.routes import sessions as sessions_route
from app.core.context import tenant_context
from app.core.memory.history import HistoryManager
from app.core.memory.session_store import SessionStore
from app.core.memory.session_title_generator import (
    SessionTitleGenerator,
    build_fallback_title,
    is_substantive_message,
    sanitize_title,
)


def _make_fake_llm(reply: object):
    llm = MagicMock()
    if isinstance(reply, Exception):
        llm.ainvoke = AsyncMock(side_effect=reply)
    else:
        llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=reply))
    return lambda: llm


def test_t0_fallback_title_greeting_filler_and_pii_masking():
    assert is_substantive_message("你好") is False
    assert is_substantive_message("在吗？") is False
    assert is_substantive_message("ok!") is False
    assert build_fallback_title("你好，在吗？") == "新对话"

    q = "你好，请帮我核查患者：张三，身份证 110101199003072345，手机 13812345678 的骨科耗材重复收费。"
    title = build_fallback_title(q, max_len=24)
    assert not title.startswith("你好")
    assert not title.startswith("请帮我")
    assert "110101199003072345" not in title
    assert "13812345678" not in title
    assert "张**" in title
    assert len(title) <= 24

    cleaned = sanitize_title("《骨科耗材超限核查》。", max_len=20)
    assert cleaned == "骨科耗材超限核查"


@pytest.mark.asyncio
async def test_t1_llm_title_refinement_sanitization_and_graceful_fallback(tmp_path):
    noisy_reply = "<thought>分析一下</thought>\n标题：《市一医院促红素超频次核查》，\n手机 13812345678"
    gen_ok = SessionTitleGenerator(llm_factory=_make_fake_llm(noisy_reply))
    refined = await gen_ok.generate_llm_title("查一下市一医院促红素开药频次", "已锁定违规记录")
    assert refined is not None
    assert "<thought>" not in refined
    assert "标题" not in refined
    assert "13812345678" not in refined
    assert len(refined) <= 20

    gen_err = SessionTitleGenerator(llm_factory=_make_fake_llm(RuntimeError("upstream 502")))
    assert await gen_err.generate_llm_title("排查男性结算妇科药") is None

    async def slow_ainvoke(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return SimpleNamespace(content="超长超时结果")

    slow_llm = MagicMock()
    slow_llm.ainvoke = slow_ainvoke
    gen_timeout = SessionTitleGenerator(llm_factory=lambda: slow_llm)
    assert await gen_timeout.generate_llm_title("排查分解住院", timeout_seconds=0.02) is None


@pytest.mark.asyncio
async def test_t2_manual_rename_locks_against_llm_overwrite(tmp_path):
    gen = SessionTitleGenerator(llm_factory=_make_fake_llm("男性结算妇科药核查"))
    store = SessionStore(db_path=str(tmp_path / "sessions.db"), title_generator=gen)

    meta = store.record_turn("sess_t2", "请帮我查一下男性结算妇科专属药品的情况", "已排查完毕")
    assert meta["title_source"] == "fallback"
    assert meta["should_refine_title"] is True

    updated = store.update_session("sess_t2", title="骨科专项核查-人工锁定")
    assert updated["title"] == "骨科专项核查-人工锁定"
    assert updated["title_source"] == "manual"

    assert store.update_title_from_llm("sess_t2", "模型覆盖标题") is False
    assert await store.refine_title_in_background("sess_t2", "q", "a") is None
    assert store.get_session("sess_t2")["title"] == "骨科专项核查-人工锁定"


@pytest.mark.asyncio
async def test_deferred_title_refinement_after_greeting_turn(tmp_path):
    gen = SessionTitleGenerator(llm_factory=_make_fake_llm("男性妇科用药违规核查"))
    store = SessionStore(db_path=str(tmp_path / "sessions.db"), title_generator=gen)

    turn1 = store.record_turn("sess_greet", "你好", "您好，请问有什么审计需求？")
    assert turn1["title"] == "新对话"
    assert turn1["should_refine_title"] is False

    turn2 = store.record_turn("sess_greet", "帮我核查男性结算妇科专属药品明细", "正在分析...")
    assert turn2["title"] != "新对话"
    assert turn2["title_source"] == "fallback"
    assert turn2["should_refine_title"] is True

    refined = await store.refine_title_in_background("sess_greet", "帮我核查男性结算妇科专属药品明细", "正在分析...")
    assert refined == "男性妇科用药违规核查"
    saved = store.get_session("sess_greet")
    assert saved["title"] == "男性妇科用药违规核查"
    assert saved["title_source"] == "llm"


@pytest.mark.asyncio
async def test_session_store_crud_tenant_isolation_and_cascade_delete(tmp_path):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))

    token_a = tenant_context.set("tenant-a")
    try:
        store.record_turn("s1", "排查市一医院麻醉收费合规问题", "结果1", domain="audit")
        store.record_turn("s2", "起草建设工程施工合同补充协议", "结果2", domain="legal")
        history_mgr.save_turn("s1", "排查市一医院麻醉收费合规问题", "结果1")
        store.update_session("s1", pinned=True)
    finally:
        tenant_context.reset(token_a)

    token_b = tenant_context.set("tenant-b")
    try:
        store.record_turn("s3", "查看其他租户的医保结算明细", "结果3")
        assert store.get_session("s1") is None
        assert store.list_sessions()["total"] == 1
    finally:
        tenant_context.reset(token_b)

    listed_a = store.list_sessions(tenant_id="tenant-a")
    assert listed_a["total"] == 2
    assert listed_a["items"][0]["session_id"] == "s1"
    assert store.list_sessions(tenant_id="tenant-a", domain="legal")["total"] == 1
    assert store.list_sessions(tenant_id="tenant-a", query="麻醉")["total"] == 1

    store.update_session("s2", archived=True, tenant_id="tenant-a")
    assert store.list_sessions(tenant_id="tenant-a", include_archived=False)["total"] == 1
    assert store.list_sessions(tenant_id="tenant-a", include_archived=True)["total"] == 2

    mock_cp = MagicMock()
    mock_cp.adelete_thread = AsyncMock(return_value=None)
    assert await store.delete_session_cascade("s1", tenant_id="tenant-a", history_mgr=history_mgr, checkpointer=mock_cp)
    assert store.get_session("s1", tenant_id="tenant-a") is None
    assert history_mgr.get_history("s1") == []
    mock_cp.adelete_thread.assert_awaited_once_with("s1")


def test_session_rest_api_endpoints_and_envelopes(tmp_path, monkeypatch):
    gen = SessionTitleGenerator(llm_factory=_make_fake_llm("骨科耗材重复收费核查"))
    store = SessionStore(db_path=str(tmp_path / "sessions.db"), title_generator=gen)
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))

    store.record_turn("api_s1", "核查骨科高值耗材重复收费问题", "核查报告A", domain="audit")
    history_mgr.save_turn("api_s1", "核查骨科高值耗材重复收费问题", "核查报告A")
    store.record_turn("api_s2", "买卖合同违约金上限司法解释", "法律意见B", domain="legal")

    mock_saver = MagicMock()
    mock_saver.adelete_thread = AsyncMock(return_value=None)

    app = FastAPI()
    register_api_exception_handlers(app)
    app.state.saver = mock_saver
    app.include_router(sessions_route.router)

    monkeypatch.setattr(sessions_route, "session_store", store)
    monkeypatch.setattr(sessions_route, "history_manager", history_mgr)
    client = TestClient(app, raise_server_exceptions=False)

    resp_list = client.get("/agent/sessions", params={"domain": "audit"})
    assert resp_list.status_code == 200
    assert resp_list.json()["data"]["total"] == 1

    resp_detail = client.get("/ins-fqz/agent/sessions/api_s1")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()["data"]
    assert detail["session_id"] == "api_s1"
    assert len(detail["messages"]) == 2

    resp_regen = client.post("/agent/sessions/api_s1/regenerate-title")
    assert resp_regen.status_code == 200
    assert resp_regen.json()["data"]["title"] == "骨科耗材重复收费核查"
    assert resp_regen.json()["data"]["title_source"] == "llm"

    resp_patch = client.patch("/agent/sessions/api_s1", json={"title": "人工定名", "pinned": True})
    assert resp_patch.status_code == 200
    assert resp_patch.json()["data"]["title_source"] == "manual"
    assert resp_patch.json()["data"]["pinned"] is True

    resp_bad_patch = client.patch("/agent/sessions/api_s1", json={"title": "   "})
    assert resp_bad_patch.status_code == 400

    resp_del = client.delete("/agent/sessions/api_s1")
    assert resp_del.status_code == 200
    assert resp_del.json()["data"]["deleted"] is True
    mock_saver.adelete_thread.assert_awaited_once_with("api_s1")

    assert client.get("/agent/sessions/api_s1").status_code == 404
    assert client.delete("/agent/sessions/api_s1").status_code == 404


@pytest.mark.asyncio
async def test_sse_session_title_and_coordinator_background_scheduling(tmp_path):
    evt = SSEEvent(event=SSEEventType.SESSION_TITLE, data={"session_id": "s1", "title": "排查大额结算"})
    assert evt.to_sse_packet().startswith("event: session_title\n")
    assert evt.to_legacy_packet() == "[[[TITLE:排查大额结算]]]"

    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    coordinator = ChatStreamCoordinator()
    mock_executor = MagicMock()
    mock_snapshot = MagicMock(next=[], values={})
    mock_executor.aget_state = AsyncMock(return_value=mock_snapshot)

    async def fake_stream_events(*_args, **_kwargs):
        yield {
            "event": "on_chain_end",
            "name": "REPORTER",
            "metadata": {"langgraph_node": "REPORTER"},
            "data": {"output": {"messages": [MagicMock(content="最终审计结论")]}},
        }

    mock_executor.astream_events = fake_stream_events
    mock_req = MagicMock(spec=Request)
    mock_req.app.state.saver = None
    mock_req.headers = {"accept": "text/event-stream"}
    mock_req.query_params = {}
    mock_bg = MagicMock(spec=BackgroundTasks)

    with (
        patch("app.api.chat_stream_coordinator.get_graph_executor", return_value=(mock_executor, "qwen-max")),
        patch("app.api.chat_stream_coordinator.session_store", store),
        patch("app.core.memory.history.HistoryManager.get_history", return_value=[]),
        patch("app.core.memory.history.HistoryManager.save_turn"),
        patch("app.core.memory.history.HistoryManager.dump_debug_history"),
    ):
        chunks = [
            c
            async for c in coordinator.coordinate_stream(
                request=mock_req,
                background_tasks=mock_bg,
                session_id="sse_title_sess",
                model_id="qwen-max",
                message="请核查某三甲医院骨科耗材重复收费明细",
                stream_format="sse",
            )
        ]

    output = "".join(chunks)
    assert "event: session_title\n" in output
    mock_bg.add_task.assert_called_once()
    assert mock_bg.add_task.call_args.args[0] == store.refine_title_in_background
