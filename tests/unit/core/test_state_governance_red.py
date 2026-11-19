"""
tests/unit/core/test_state_governance_red.py
============================================
红灯测试：多轮会话状态清洗机制标准化与 AuditState 生命周期治理
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from app.core.state import (
    AuditState,
    build_initial_audit_state,
    create_turn_reset_patch,
    filter_state_for_logging,
)


def test_build_initial_audit_state():
    """测试标准初始状态创建"""
    state = build_initial_audit_state(
        user_query="核查男性结算妇科专属药品",
        session_id="sess_test_123",
        metadata={"user_id": "auditor_01"}
    )
    assert state["session_id"] == "sess_test_123"
    assert len(state["messages"]) == 1
    assert isinstance(state["messages"][0], HumanMessage)
    assert state["messages"][0].content == "核查男性结算妇科专属药品"
    assert state["retry_count"] == 0
    assert state["error_log"] is None
    assert state["sql_query"] == ""
    assert state["raw_data"] == ""
    assert state["sql_validated"] is False
    assert state["metadata"]["user_question"] == "核查男性结算妇科专属药品"
    assert state["metadata"]["user_id"] == "auditor_01"


def test_create_turn_reset_patch():
    """测试多轮轮末状态重置补丁"""
    dirty_state = {
        "sql_query": "SELECT * FROM dirty_table",
        "raw_data": "[{'dirty': 'data'}]",
        "error_log": "SyntaxError",
        "retry_count": 2,
        "execution_trace": ["step1", "step2"],
        "sql_validated": True,
        "current_turn_query": "上一轮问题",
        "turn_type": "QUERY",
        "metadata": {
            "synthesis_done": True,
            "fast_route_id": "direct_123",
            "direct_response": "done",
            "user_id": "auditor_01"
        }
    }
    patch = create_turn_reset_patch(dirty_state)
    assert patch["sql_query"] == ""
    assert patch["raw_data"] == ""
    assert patch["error_log"] is None
    assert patch["retry_count"] == 0
    assert patch["execution_trace"] == []
    assert patch["sql_validated"] is False
    assert patch["current_turn_query"] is None
    assert patch["turn_type"] is None
    # 验证 metadata 中的单轮临时标记被清洗，保留业务全局上下文
    assert patch["metadata"]["synthesis_done"] is False
    assert patch["metadata"]["fast_route_id"] is None
    assert patch["metadata"]["direct_response"] is None
    assert patch["metadata"]["user_id"] == "auditor_01"


def test_filter_state_for_logging():
    """测试用于日志记录的状态安全脱敏与过长截断"""
    state = {
        "session_id": "sess_999",
        "sql_query": "SELECT count(*) FROM fqz_fymx_test",
        "raw_data": "x" * 5000,
        "metadata": {"certno": "110101199003072345", "user_question": "查询患者"}
    }
    safe_log = filter_state_for_logging(state, max_raw_data_len=100)
    assert safe_log["session_id"] == "sess_999"
    assert len(safe_log["raw_data"]) < 200
    assert "...[TRUNCATED" in safe_log["raw_data"]
    # 敏感字段脱敏
    assert safe_log["metadata"]["certno"] != "110101199003072345"
