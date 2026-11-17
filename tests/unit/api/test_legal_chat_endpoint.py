import pytest
import json
from starlette.testclient import TestClient
from app.main import app

def test_legal_chat_stream_endpoint():
    with TestClient(app) as client:
        req_body = {
            "thread_id": "test-session-api",
            "message": "张三持借条向法院起诉李四要求归还借款20万元，有银行转账记录流水。",
            "cause_of_action": "民间借贷纠纷"
        }
        response = client.post("/legal/chat", json=req_body)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        content = response.text
        assert "data:" in content
        assert "ALIGNER" in content
        assert "PLANNER" in content
        assert "GATE" in content
        assert "REPORTER" in content
        assert "[DONE]" in content
