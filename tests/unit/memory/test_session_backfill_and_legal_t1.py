"""
tests/unit/memory/test_session_backfill_and_legal_t1.py
=========================================================
Offline unit tests for lossless HistoryManager retention, legacy JSON
backfill indexing, REST backfill endpoint, and legal stream T1 title refinement.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI
from starlette.testclient import TestClient

from app.api.envelope import register_api_exception_handlers
from app.api.legal_stream_coordinator import LegalStreamCoordinator
from app.api.routes import sessions as sessions_route
from app.core.memory.history import HistoryManager
from app.core.memory.session_backfill import backfill_legacy_history, infer_session_domain
from app.core.memory.session_store import SessionStore


def test_history_manager_lossless_by_default_and_limit_option(tmp_path):
    mgr = HistoryManager(storage_dir=str(tmp_path / "hist"))
    for i in range(15):
        mgr.save_turn("long_sess", f"问题 {i}", f"回答 {i}")

    full = mgr.get_history("long_sess")
    assert len(full) == 30
    assert full[0].content == "问题 0"
    assert full[-1].content == "回答 14"

    recent = mgr.get_history("long_sess", limit=4)
    assert len(recent) == 4
    assert recent[0].content == "问题 13"

    capped = HistoryManager(storage_dir=str(tmp_path / "hist_cap"), max_messages=4)
    for i in range(4):
        capped.save_turn("cap_sess", f"Q{i}", f"A{i}")
    assert len(capped.get_history("cap_sess")) == 4
    assert capped.get_history("cap_sess")[0].content == "Q2"


def test_backfill_legacy_history_imports_and_is_idempotent(tmp_path):
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))

    history_mgr.save_turn("audit-old-1", "患者：张三 13812345678 核查骨水泥重复收费", "已发现异常 5 笔")
    history_mgr.save_turn("legal-old-2", "借款人逾期未还本金及利息如何起诉", "依据民法典分析如下")
    history_mgr.save_messages("empty-old-3", [])
    (tmp_path / "history" / "audit-old-1.json.tmp.999").write_text("[]", encoding="utf-8")

    os.utime(history_mgr._get_path("audit-old-1"), (1700000000, 1700000000))

    summary = backfill_legacy_history(store, history_mgr)
    assert summary["scanned"] == 3
    assert summary["imported"] == 2
    assert summary["empty_skipped"] == 1
    assert summary["errors"] == 0

    audit_row = store.get_session("audit-old-1")
    legal_row = store.get_session("legal-old-2")
    assert audit_row["domain"] == "audit"
    assert "13812345678" not in audit_row["title"]
    assert "13812345678" not in audit_row["last_message_preview"]
    assert audit_row["updated_at"].startswith("2023-11-14")
    assert legal_row["domain"] == "legal"

    store.update_session("audit-old-1", title="人工锁定旧审计标题")
    second = backfill_legacy_history(store, history_mgr)
    assert second["imported"] == 0
    assert second["skipped"] == 2
    assert store.get_session("audit-old-1")["title"] == "人工锁定旧审计标题"
    assert infer_session_domain("random-id", history_mgr.get_history("legal-old-2")) == "legal"


def test_session_backfill_rest_endpoint(tmp_path, monkeypatch):
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr.save_turn("legacy_api_1", "排查市一医院麻醉收费合规问题", "核查完成")

    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(sessions_route.router)
    monkeypatch.setattr(sessions_route, "session_store", store)
    monkeypatch.setattr(sessions_route, "history_manager", history_mgr)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/agent/sessions/backfill")
    assert resp.status_code == 200
    assert resp.json()["data"]["imported"] == 1
    assert client.get("/ins-fqz/agent/sessions/legacy_api_1").status_code == 200


@pytest.mark.asyncio
async def test_legal_stream_schedules_t1_title_refinement(tmp_path):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"))

    async def fake_areview(msg: str):
        return f"合同审查结论：{msg[:20]}", {"prompt": 10, "completion": 20}

    fake_reviewer = MagicMock()
    fake_reviewer.areview = fake_areview

    coord = LegalStreamCoordinator()
    coord._graph = MagicMock()
    coord._graph.aget_state = AsyncMock(return_value=MagicMock(next=[], values={}))
    bg_tasks = MagicMock(spec=BackgroundTasks)

    with (
        patch("app.api.legal_stream_coordinator.session_store", store),
        patch("app.api.legal_stream_coordinator.history_manager", history_mgr),
        patch.dict(
            "app.api.legal_stream_coordinator._DIRECT_MODE_SPECS",
            {"contract_review": ("审查中...", "REVIEWER", fake_reviewer, "areview")},
        ),
    ):
        chunks = [
            c
            async for c in coord.coordinate_legal_stream(
                session_id="legal_t1_sess",
                message="【模式：合同审查】核查建设工程施工合同违约金条款风险",
                background_tasks=bg_tasks,
            )
        ]

    assert any("合同审查结论" in c for c in chunks)
    bg_tasks.add_task.assert_called_once()
    args = bg_tasks.add_task.call_args
    assert args.args[0] == store.refine_title_in_background
    assert args.kwargs.get("domain") == "legal"

    bg_tasks.reset_mock()
    store.update_session("legal_t1_sess", title="人工锁定法律标题")
    with (
        patch("app.api.legal_stream_coordinator.session_store", store),
        patch("app.api.legal_stream_coordinator.history_manager", history_mgr),
        patch.dict(
            "app.api.legal_stream_coordinator._DIRECT_MODE_SPECS",
            {"contract_review": ("审查中...", "REVIEWER", fake_reviewer, "areview")},
        ),
    ):
        _ = [
            c
            async for c in coord.coordinate_legal_stream(
                session_id="legal_t1_sess",
                message="【模式：合同审查】补充核查保证金条款",
                background_tasks=bg_tasks,
            )
        ]
    bg_tasks.add_task.assert_not_called()
