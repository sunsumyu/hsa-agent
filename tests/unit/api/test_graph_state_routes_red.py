"""
tests/unit/api/test_graph_state_routes_red.py
=============================================
Unit tests for graph_state.py and palace.py routes:
- /agent/update_state
- /agent/fork
- /palace/timeline
- /palace/conflicts
- /palace/conflicts/resolve
- /palace/graph
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.routes.graph_state as graph_state_module
import app.routes.palace as palace_module
from app.routes.graph_state import router as graph_state_router
from app.routes.palace import router as palace_router


@pytest.fixture
def graph_api_client(monkeypatch):
    mock_orchestrator = MagicMock()
    mock_orchestrator.intervene_findings = AsyncMock(return_value={"status": "success", "message": "状态已更新"})
    mock_orchestrator.fork_session = AsyncMock(return_value={"status": "success", "targetSession": "tgt_123"})
    mock_orchestrator.get_timeline_events = AsyncMock(return_value=[{"step": "PLANNER", "time": "2026-10-18T10:00:00"}])

    monkeypatch.setattr(graph_state_module, "graph_state_orchestrator", mock_orchestrator)
    monkeypatch.setattr(palace_module, "graph_state_orchestrator", mock_orchestrator)

    app = FastAPI()
    app.include_router(graph_state_router)
    app.include_router(palace_router)
    return TestClient(app), mock_orchestrator


def test_agent_update_state(graph_api_client):
    client, mock_orchestrator = graph_api_client

    resp = client.post(
        "/agent/update_state",
        headers={"X-Session-Id": "my_test_session"},
        json={"findings": ["Finding A", "Finding B"]}
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    mock_orchestrator.intervene_findings.assert_awaited_once_with(
        session_id="my_test_session",
        findings=["Finding A", "Finding B"],
        checkpointer=None,
    )


def test_agent_fork(graph_api_client):
    client, mock_orchestrator = graph_api_client

    resp = client.post(
        "/agent/fork",
        json={"sourceSessionId": "sess_src", "targetSessionId": "sess_tgt"}
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["targetSession"] == "tgt_123"
    mock_orchestrator.fork_session.assert_awaited_once_with(
        source_session="sess_src",
        target_session="sess_tgt",
        checkpointer=None,
    )


def test_palace_timeline(graph_api_client):
    client, mock_orchestrator = graph_api_client

    resp = client.get("/palace/timeline?session_id=sess_time")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess_time"
    assert len(data["events"]) == 1
    assert data["events"][0]["step"] == "PLANNER"
    mock_orchestrator.get_timeline_events.assert_awaited_once_with(
        "sess_time",
        checkpointer=None,
    )


def test_palace_conflicts_and_resolve(graph_api_client, monkeypatch):
    client, _ = graph_api_client

    mock_detect = MagicMock(return_value=[{"conflict": "mock_conflict"}])
    mock_resolve = MagicMock()

    monkeypatch.setattr("app.skills.conflict_detector.detect_conflicts", mock_detect)
    monkeypatch.setattr("app.skills.conflict_detector.mark_resolved", mock_resolve)

    # GET /palace/conflicts
    resp_conf = client.get("/palace/conflicts")
    assert resp_conf.status_code == 200
    assert len(resp_conf.json()["conflicts"]) == 1

    # POST /palace/conflicts/resolve
    resp_res = client.post(
        "/palace/conflicts/resolve",
        json={
            "finding_a": "finding_1",
            "keep_a": True,
            "finding_b": "finding_2",
            "keep_b": False,
        }
    )
    assert resp_res.status_code == 200
    assert resp_res.json()["status"] == "success"
    assert mock_resolve.call_count == 2


def test_palace_graph_endpoint(graph_api_client, monkeypatch):
    client, _ = graph_api_client

    mock_graph_manager = MagicMock()
    mock_graph_manager.get_session_graph.return_value = {
        "nodes": [{"id": "H_1", "name": "市一院", "category": 0}],
        "edges": [],
        "categories": [],
        "total": 1,
    }

    monkeypatch.setattr(palace_module, "evidence_graph_manager", mock_graph_manager)

    resp = client.get("/palace/graph?session_id=sess_graph_123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["nodes"][0]["name"] == "市一院"
    mock_graph_manager.get_session_graph.assert_called_once_with("sess_graph_123")

