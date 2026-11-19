# -*- coding: utf-8 -*-
"""
tests/unit/api/test_chat_feedback_endpoint_red.py
==================================================
[TDD Red -> Green] API 反馈闭环与元数据包渲染契约测试
Driven by: Matt Pocock Thin Controller & Deep Module Principles

测试项：
1. render_meta_envelope 正确生成前端协议帧 :::meta {"run_id": "...", ...}:::
2. POST /agent/feedback 与 POST /ins-fqz/agent/feedback 接口正常接收并记录反馈
3. 校验 score 在 [0.0, 1.0] 闭区间，超范围触发 422 验证异常
"""

import json
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from app.routes.chat import router as chat_router
from app.core.container import ServiceProvider
from tests.conftest import InMemoryObservabilityFake


@pytest.fixture
def isolated_chat_client():
    """轻量隔离的 Chat 路由测试客户端"""
    fake = InMemoryObservabilityFake()
    ServiceProvider.override("observability", fake)

    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    yield client, fake

    ServiceProvider.clear_overrides("observability")


def test_render_meta_envelope_format():
    """断言 1: render_meta_envelope 渲染合法 JSON 协议帧"""
    from app.api.stream_protocol_renderer import stream_protocol_renderer
    assert hasattr(stream_protocol_renderer, "render_meta_envelope"), "缺失 render_meta_envelope 契约方法"

    frame = stream_protocol_renderer.render_meta_envelope(
        run_id="run-test-999",
        session_id="sess-audit-001"
    )
    assert frame.startswith(":::meta ")
    assert frame.endswith(":::\n")

    json_str = frame.replace(":::meta ", "").replace(":::\n", "")
    data = json.loads(json_str)
    assert data["run_id"] == "run-test-999"
    assert data["session_id"] == "sess-audit-001"


def test_feedback_endpoint_success(isolated_chat_client):
    """断言 2: POST /agent/feedback 与 POST /ins-fqz/agent/feedback 正常流转到可观测服务"""
    client, fake = isolated_chat_client

    payload = {
        "run_id": "run-uuid-12345",
        "score": 1.0,
        "category": "ACCURATE",
        "comment": "保妇康栓违规判定结果与物理 ClickHouse 真值一致"
    }

    # 测试 /agent/feedback
    resp = client.post("/agent/feedback", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data.get("success") is True
    assert res_data.get("run_id") == "run-uuid-12345"

    # 测试兼容别名路径 /ins-fqz/agent/feedback
    resp_alias = client.post("/ins-fqz/agent/feedback", json=payload)
    assert resp_alias.status_code == 200

    # 断言 fake 成功捕获了 2 次反馈记录
    assert len(fake.recorded_feedbacks) == 2
    assert fake.recorded_feedbacks[0]["run_id"] == "run-uuid-12345"
    assert fake.recorded_feedbacks[0]["score"] == 1.0


def test_feedback_endpoint_validation_error(isolated_chat_client):
    """断言 3: score 超出 [0.0, 1.0] 触发 422 校验拒绝"""
    client, _ = isolated_chat_client

    bad_payload = {
        "run_id": "run-uuid-12345",
        "score": 2.5,  # 非法超标评分
    }
    resp = client.post("/agent/feedback", json=bad_payload)
    assert resp.status_code == 422
