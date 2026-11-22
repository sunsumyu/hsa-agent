"""
tests/unit/api/test_api_envelope_standardization_red.py
======================================================
[TDD Red -> Green] API 响应信封与控制器异常边界标准化测试：
1. ResponseEnvelope.from_result 深度封装 (自动将服务层字典转化为标准信封)
2. graph_state 路由标准化测试 (/agent/update_state, /agent/fork)
3. misc 路由标准信封化测试 (/agent/models/probe, /agent/trajectory)
4. 全局异常拦截穿透测试 (Thin Controller, 无需手动 try...except 捕获 500)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.envelope import ResponseEnvelope, register_api_exception_handlers
from app.routes.graph_state import router as graph_state_router
from app.routes.misc import router as misc_router


@pytest.fixture
def api_test_app():
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(graph_state_router)
    app.include_router(misc_router)
    return app


@pytest.fixture
def client(api_test_app):
    return TestClient(api_test_app, raise_server_exceptions=False)


def test_response_envelope_from_result_success():
    """验证 from_result 转换业务层成功字典"""
    service_res = {
        "status": "success",
        "message": "状态已更新",
        "targetSession": "session-xyz",
    }
    resp = ResponseEnvelope.from_result(service_res)
    assert resp.status_code == 200
    import json
    data = json.loads(resp.body.decode("utf-8"))
    assert data["ok"] is True
    assert data["status"] == "success"
    assert data["message"] == "状态已更新"
    assert data["targetSession"] == "session-xyz"


def test_response_envelope_from_result_error():
    """验证 from_result 转换业务层失败字典自动置 400/error 信封"""
    service_res = {
        "status": "error",
        "message": "源会话不存在",
    }
    resp = ResponseEnvelope.from_result(service_res, error_status_code=404)
    assert resp.status_code == 404
    import json
    data = json.loads(resp.body.decode("utf-8"))
    assert data["ok"] is False
    assert data["error"] == "源会话不存在"
    assert data["status"] == "error"


def test_update_state_success(client, monkeypatch):
    """测试 /agent/update_state 成功返回统一信封"""
    from app.orchestration.graph_state_orchestrator import graph_state_orchestrator
    async def mock_intervene(*args, **kwargs):
        return {"status": "success", "message": "状态已更新，下次推演将使用新线索"}
    monkeypatch.setattr(graph_state_orchestrator, "intervene_findings", mock_intervene)

    resp = client.post(
        "/agent/update_state",
        json={"findings": ["发现虚假就医"]},
        headers={"X-Session-Id": "sess-001"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "状态已更新" in body.get("message", "")


def test_update_state_session_not_found(client, monkeypatch):
    """测试 /agent/update_state 会话不存在时返回标准 404 错误信封"""
    from app.orchestration.graph_state_orchestrator import graph_state_orchestrator
    async def mock_intervene(*args, **kwargs):
        return {"status": "error", "message": "会话不存在或未初始化"}
    monkeypatch.setattr(graph_state_orchestrator, "intervene_findings", mock_intervene)

    resp = client.post(
        "/agent/update_state",
        json={"findings": ["新线索"]},
        headers={"X-Session-Id": "sess-nonexistent"}
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert "会话不存在" in body.get("error", "")


def test_fork_session_success(client, monkeypatch):
    """测试 /agent/fork 成功返回统一信封"""
    from app.orchestration.graph_state_orchestrator import graph_state_orchestrator
    async def mock_fork(*args, **kwargs):
        return {"status": "success", "targetSession": "sess-child-1"}
    monkeypatch.setattr(graph_state_orchestrator, "fork_session", mock_fork)

    resp = client.post(
        "/agent/fork",
        json={"sourceSessionId": "sess-parent", "targetSessionId": "sess-child-1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body.get("targetSession") == "sess-child-1"


def test_fork_session_source_not_found(client, monkeypatch):
    """测试 /agent/fork 源会话不存在时返回 404 错误信封"""
    from app.orchestration.graph_state_orchestrator import graph_state_orchestrator
    async def mock_fork(*args, **kwargs):
        return {"status": "error", "message": "源会话不存在"}
    monkeypatch.setattr(graph_state_orchestrator, "fork_session", mock_fork)

    resp = client.post(
        "/agent/fork",
        json={"sourceSessionId": "missing-parent", "targetSessionId": "sess-child-2"}
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert "源会话不存在" in body.get("error", "")


def test_misc_probe_models_enveloped(client, monkeypatch):
    """测试 /agent/models/probe 返回统一信封"""
    from app.infra.model_manager import model_manager
    async def mock_probe():
        pass
    monkeypatch.setattr(model_manager, "probe_all_endpoints", mock_probe)

    resp = client.post("/agent/models/probe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "全量自检" in body.get("message", "")


def test_misc_trajectory_enveloped(client):
    """测试 /agent/trajectory 返回统一信封"""
    resp = client.get("/agent/trajectory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body.get("status") == "deprecated"
