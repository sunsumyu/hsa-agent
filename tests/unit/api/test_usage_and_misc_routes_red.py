"""
tests/unit/api/test_usage_and_misc_routes_red.py
================================================
Unit tests for usage and misc API routes and ResponseEnvelope deep module:
- /api/usage/stats
- /api/usage/reset-blacklists
- /agent/models
- /agent/metrics & /agent/statistics
- /agent/history
- /agent/trajectory
- ResponseEnvelope & APIExceptionHandler contracts
"""

import pytest
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from app.routes.usage import router as usage_router
from app.routes.misc import router as misc_router
from app.api.envelope import ResponseEnvelope, register_api_exception_handlers


@pytest.fixture
def app_client():
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(usage_router)
    app.include_router(misc_router)
    return TestClient(app, raise_server_exceptions=False)


def test_usage_stats_and_reset(app_client):
    # GET /api/usage/stats
    resp = app_client.get("/api/usage/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "data" in data
    assert "total_daily_tokens" in data["data"]
    assert "nodes" in data["data"]

    # POST /api/usage/reset-blacklists
    resp_reset = app_client.post("/api/usage/reset-blacklists")
    assert resp_reset.status_code == 200
    assert resp_reset.json()["ok"] is True


def test_misc_routes(app_client):
    # GET /agent/models
    resp_models = app_client.get("/agent/models")
    assert resp_models.status_code == 200
    assert isinstance(resp_models.json(), list)

    # GET /agent/metrics
    resp_metrics = app_client.get("/agent/metrics")
    assert resp_metrics.status_code == 200
    metrics_data = resp_metrics.json()
    assert "date" in metrics_data
    assert "models" in metrics_data

    # GET /agent/history
    resp_hist = app_client.get("/agent/history", headers={"X-Session-Id": "test_session_xyz"})
    assert resp_hist.status_code == 200
    assert isinstance(resp_hist.json(), list)

    # GET /agent/trajectory
    resp_traj = app_client.get("/agent/trajectory")
    assert resp_traj.status_code == 200
    assert resp_traj.json()["status"] == "deprecated"


def test_usage_stats_error_enveloped(app_client, monkeypatch):
    from app.infra.usage_tracker import usage_tracker
    def raise_err():
        raise RuntimeError("UsageTracker failure")
    monkeypatch.setattr(usage_tracker, "get_governance_snapshot", raise_err)

    resp = app_client.get("/api/usage/stats")
    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "UsageTracker failure" in data.get("error", "")


def test_usage_reset_blacklists_error_enveloped(app_client, monkeypatch):
    from app.infra.usage_tracker import usage_tracker
    def raise_reset_err():
        raise RuntimeError("Reset failed")
    monkeypatch.setattr(usage_tracker, "reset_blacklists", raise_reset_err)

    resp = app_client.post("/api/usage/reset-blacklists")
    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "Reset failed" in data.get("error", "")


def test_response_envelope_contracts():
    # 1. 成功信封契约
    succ = ResponseEnvelope.success(data={"items": [1, 2, 3]}, message="Query ok")
    assert succ.status_code == 200
    import json
    succ_data = json.loads(succ.body.decode("utf-8"))
    assert succ_data["ok"] is True
    assert succ_data["message"] == "Query ok"
    assert succ_data["data"] == {"items": [1, 2, 3]}

    # 2. 失败信封契约
    err = ResponseEnvelope.error(error="Bad parameter", status_code=400, details={"field": "strategy"})
    assert err.status_code == 400
    err_data = json.loads(err.body.decode("utf-8"))
    assert err_data["ok"] is False
    assert err_data["error"] == "Bad parameter"
    assert err_data["details"] == {"field": "strategy"}


def test_api_exception_handler_middleware():
    test_app = FastAPI()
    register_api_exception_handlers(test_app)

    @test_app.get("/test/val-error")
    def route_val_error():
        raise ValueError("Invalid strategy parameter")

    @test_app.get("/test/key-error")
    def route_key_error():
        raise KeyError("user_id")

    @test_app.get("/test/http-error")
    def route_http_error():
        raise HTTPException(status_code=403, detail="Access forbidden")

    @test_app.get("/test/runtime-error")
    def route_runtime_error():
        raise RuntimeError("Database connection dropped")

    client = TestClient(test_app, raise_server_exceptions=False)

    # 1. 验证 ValueError -> 400
    r_val = client.get("/test/val-error")
    assert r_val.status_code == 400
    assert r_val.json()["ok"] is False
    assert "Invalid strategy parameter" in r_val.json()["error"]

    # 2. 验证 KeyError -> 404
    r_key = client.get("/test/key-error")
    assert r_key.status_code == 404
    assert r_key.json()["ok"] is False
    assert "user_id" in r_key.json()["error"]

    # 3. 验证 HTTPException -> 对应状态码 (403)
    r_http = client.get("/test/http-error")
    assert r_http.status_code == 403
    assert r_http.json()["ok"] is False
    assert "Access forbidden" in r_http.json()["error"]

    # 4. 验证通用未捕获异常 -> 500
    r_rt = client.get("/test/runtime-error")
    assert r_rt.status_code == 500
    assert r_rt.json()["ok"] is False
    assert "Database connection dropped" in r_rt.json()["error"]
