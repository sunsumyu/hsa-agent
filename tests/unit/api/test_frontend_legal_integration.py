"""
tests/unit/api/test_frontend_legal_integration.py
==================================================
测试 argus-frontend (Rust Yew/WASM) 与后端 Legal Agent 接口全面打通契约:
1. GET /agent/models: 包含置顶的 'legal-agent' 及其元数据
2. POST /agent/chat (显式 modelId='legal-agent'): 前端协议事件流 (ENGINE, STATUS, Markdown, RESOURCE)
3. POST /agent/chat (自动路由 modelId='auto' + 法律意图关键词): 智能路由到 Legal Agent
4. GET /agent/history: 正确拉取历史记录
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.routes.misc import router as misc_router
from app.routes.chat import router as chat_router
from app.api.envelope import register_api_exception_handlers


@pytest.fixture
def api_client():
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(misc_router)
    app.include_router(chat_router)
    return TestClient(app, raise_server_exceptions=False)


def test_models_endpoint_contains_legal_agent(api_client):
    """验证 GET /agent/models 包含 legal-agent 且具备前端所需全量字段"""
    resp = api_client.get("/agent/models")
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list)
    assert len(models) > 0

    legal_model = next((m for m in models if m["id"] == "legal-agent"), None)
    assert legal_model is not None
    assert legal_model["name"] == "⚖️ 法律辩法智能体 (三段论与红蓝对抗)"
    assert legal_model["provider"] == "Argus-Legal"
    assert legal_model["tools_support"] is True
    assert legal_model["priority"] >= 100
    assert legal_model["is_available"] is True
    assert "时效" in legal_model["status_msg"]


def test_chat_stream_explicit_legal_model(api_client):
    """验证前端选择 legal-agent 发起对话时的完整 SSE 协议流"""
    payload = {
        "input": "张三向李四借款10万元并出具借条，约定年利率36%，借期1年，已逾期3年半未催告。",
        "modelId": "legal-agent",
    }
    headers = {
        "X-Session-Id": "test-legal-fe-session-1",
        "X-Tenant-Id": "test-tenant",
    }
    resp = api_client.post("/agent/chat", json=payload, headers=headers)
    assert resp.status_code == 200
    raw_text = resp.text

    # 1. 验证前端引擎身份与状态标识
    assert "[[[ENGINE:Argus-Legal-Agent]]]" in raw_text
    assert "[[[STATUS:" in raw_text

    # 2. 验证事实认定、争议焦点、红蓝对抗与心证意见书
    assert "### 📋 一、涉案案情事实认定与证据审查" in raw_text
    assert "### 🎯 二、法定构成要件与争议焦点" in raw_text
    assert "### ⚔️ 三、法庭红蓝攻防对抗推演" in raw_text
    assert "### 🛡️ 四、神经符号法理门禁审查" in raw_text
    assert "【法官心证评判】" in raw_text

    # 3. 验证神经符号门禁刚性拦截警告 (交付凭证/诉讼时效/4倍LPR等)
    assert "法理门禁刚性拦截" in raw_text or "款项交付" in raw_text or "诉讼时效" in raw_text or "超过一年期LPR四倍" in raw_text

    # 4. 验证算力 HUD 资源数据包
    assert "[[[RESOURCE:" in raw_text
    assert "JUDGE" in raw_text


def test_chat_stream_auto_routing_legal_keywords(api_client):
    """验证自动路由模式下根据法律关键词智能直连 Legal Agent"""
    payload = {
        "input": "原告与被告签订买卖合同，约定逾期支付货款按日万分之五计付违约金，被告已签收但迟延付款。",
        "modelId": "auto",
    }
    headers = {
        "X-Session-Id": "test-legal-fe-session-2",
        "X-Tenant-Id": "test-tenant",
    }
    resp = api_client.post("/agent/chat", json=payload, headers=headers)
    assert resp.status_code == 200
    raw_text = resp.text

    assert "[[[ENGINE:Argus-Legal-Agent]]]" in raw_text
    assert "买卖合同纠纷" in raw_text
    assert "### 📋 一、涉案案情事实认定与证据审查" in raw_text


def test_history_endpoint_recovers_legal_chat(api_client):
    """验证 GET /agent/history 能够恢复法律咨询会话内容"""
    session_id = "test-legal-fe-session-hist"
    payload = {
        "input": "出借人起诉借款人归还借款本息5万元。",
        "modelId": "legal-agent",
    }
    headers = {
        "X-Session-Id": session_id,
        "X-Tenant-Id": "test-tenant",
    }
    api_client.post("/agent/chat", json=payload, headers=headers)

    # 获取历史记录
    hist_resp = api_client.get("/agent/history", headers=headers)
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert isinstance(history, list)
    assert len(history) >= 2
    assert history[0]["role"] == "user"
    assert "5万元" in history[0]["content"]
    assert history[1]["role"] == "ai"
    assert "涉案案情事实认定与证据审查" in history[1]["content"]
