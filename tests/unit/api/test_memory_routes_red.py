"""
tests/unit/api/test_memory_routes_red.py
========================================
针对 app/routes/memory.py 与 MemoryHub 遗忘引擎的 Matt Pocock 契约测试：
1. GET /api/memory/stats 健康信标
2. GET /api/memory/summary 提示词摘要
3. POST /api/memory/forget 合法参数正常淘汰
4. POST /api/memory/forget 非法 strategy 返回 400
5. POST /api/memory/forget 超界 threshold 返回 400
6. POST /api/memory/forget 非正数 max_age_days 返回 400
7. 异常熔断与降级自愈 (500 处理)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.api.routes.memory as memory_route_module
from app.api.routes.memory import router as memory_router


@pytest.fixture
def memory_client(monkeypatch):
    mock_hub = MagicMock()
    mock_hub.get_stats.return_value = {
        "version": "V4.6.0",
        "timestamp": "2026-10-18T10:00:00",
        "memory_mode": "LOCAL",
        "layers": {
            "l0_working": {"active": 5, "expired_pending_gc": 0, "backend": "In-Process + Redis"},
            "l1_semantic": {"status": "ONLINE", "backend": "FAISS"},
            "l2_episodic": {"status": "ONLINE", "backend": "SQLite"},
            "l3_perceptual": {"status": "ONLINE", "backend": "CLIP + FAISS"},
        },
        "infrastructure": {"redis": "ONLINE", "tenant_shards": 1, "model_mode": "HF_OFFLINE"},
    }
    mock_hub.get_summary.return_value = "🧠 记忆中枢 [LOCAL] | L0工作记忆: 5项活跃 | 语义/情景: ONLINE | 感知层: ONLINE"
    mock_hub.forget_memories = AsyncMock(return_value={
        "importance_evicted": 3,
        "time_evicted": 1,
        "l0_expired": 2,
    })

    # mock 掉 routes/memory.py 内部的 memory_hub
    monkeypatch.setattr("app.core.memory.manager.memory_hub", mock_hub)

    app = FastAPI()
    app.include_router(memory_router)
    return TestClient(app), mock_hub


def test_get_memory_stats_success(memory_client):
    client, mock_hub = memory_client
    resp = client.get("/api/memory/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "layers" in data["data"]
    assert data["data"]["memory_mode"] == "LOCAL"
    mock_hub.get_stats.assert_called_once()


def test_get_memory_summary_success(memory_client):
    client, mock_hub = memory_client
    resp = client.get("/api/memory/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "🧠 记忆中枢" in data["summary"]
    mock_hub.get_summary.assert_called_once()


def test_post_forget_memories_valid(memory_client):
    client, mock_hub = memory_client
    resp = client.post("/api/memory/forget?strategy=combined&threshold=0.3&max_age_days=15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["report"]["importance_evicted"] == 3
    mock_hub.forget_memories.assert_awaited_once_with(
        strategy="combined",
        threshold=0.3,
        max_age_days=15,
    )


def test_post_forget_invalid_strategy(memory_client):
    client, _ = memory_client
    resp = client.post("/api/memory/forget?strategy=invalid_strat")
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert "策略" in data["error"] or "strategy" in data["error"].lower()


def test_post_forget_out_of_bounds_threshold(memory_client):
    client, _ = memory_client
    # 阈值 > 1.0
    resp_high = client.post("/api/memory/forget?threshold=1.5")
    assert resp_high.status_code == 400
    assert resp_high.json()["ok"] is False

    # 阈值 < 0.0
    resp_low = client.post("/api/memory/forget?threshold=-0.1")
    assert resp_low.status_code == 400
    assert resp_low.json()["ok"] is False


def test_post_forget_invalid_max_age(memory_client):
    client, _ = memory_client
    resp = client.post("/api/memory/forget?max_age_days=0")
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert "天数" in data["error"] or "max_age_days" in data["error"].lower()


def test_get_memory_stats_exception_handling(memory_client):
    client, mock_hub = memory_client
    mock_hub.get_stats.side_effect = RuntimeError("Database locked")

    resp = client.get("/api/memory/stats")
    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "Database locked" in data["error"]
