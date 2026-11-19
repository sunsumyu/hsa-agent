"""
tests/unit/api/test_chat_stream_processor_red.py
================================================
Red unit tests for chat_stream processor functions.
Tests:
- parse_chat_request (multiple payload formats and header handling)
- extract_stream_chunk_text (str, dict, list with thought/reasoning)
- emit_node_status (status and world packet generation)
- emit_tool_start_events (MOVE/LOGIC/SQL/BOOKSHELF protocol frames)
- format_resource_telemetry (token cost calculation and formatting)
- format_tool_trace_packet (tool evidence tracing container)
- render_human_review_card (expert calibration help card rendering)
- classify_and_render_error (403 quota, out of token, fallback)
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock

from app.api.chat_stream import (
    parse_chat_request,
    emit_node_status,
    emit_tool_start_events,
    classify_and_render_error,
    extract_stream_chunk_text,
    format_resource_telemetry,
    format_tool_trace_packet,
    render_human_review_card,
)


class MockRequest:
    def __init__(self, body_bytes: bytes, headers: dict = None):
        self._body = body_bytes
        self.headers = headers or {}

    async def body(self):
        return self._body


@pytest.mark.asyncio
async def test_parse_chat_request_json_variants():
    # 1. input key
    req1 = MockRequest(json.dumps({"input": "排查妇科药品", "modelId": "qwen"}).encode("utf-8"))
    msg, mid, sid = await parse_chat_request(req1)
    assert msg == "排查妇科药品"
    assert mid == "qwen"
    assert sid == "default-python-session"

    # 2. query key + X-Session-Id header
    req2 = MockRequest(
        json.dumps({"query": "重复住院", "session_id": "session-123"}).encode("utf-8"),
        headers={"X-Session-Id": "header-session"}
    )
    msg, mid, sid = await parse_chat_request(req2)
    assert msg == "重复住院"
    assert sid == "session-123"

    # 3. raw string body
    req3 = MockRequest("直接发送文本".encode("utf-8"))
    msg, mid, sid = await parse_chat_request(req3)
    assert msg == "直接发送文本"
    assert mid is None


def test_extract_stream_chunk_text():
    # String
    assert extract_stream_chunk_text("hello world") == "hello world"

    # Dict
    assert extract_stream_chunk_text({"text": "abc"}) == "abc"
    assert extract_stream_chunk_text({"thought": "thinking..."}) == "thinking..."

    # List of multimodal items
    items = [
        {"type": "thought", "thought": "Step 1: check schema; "},
        {"type": "text", "text": "Step 2: generate sql"},
        {"type": "image", "url": "http://img"},  # should be ignored
        "invalid_item",  # non-dict ignored
    ]
    assert extract_stream_chunk_text(items) == "Step 1: check schema; Step 2: generate sql"

    # Empty
    assert extract_stream_chunk_text(None) == ""
    assert extract_stream_chunk_text({}) == ""


def test_emit_node_status():
    packets = emit_node_status("DATA_EXPERT", "data_expert")
    assert any("[[[STATUS:正在激活 [数据外联专家]" in p for p in packets)
    assert any("[[[MOVE:default.fqz_all_yy_yd_1]]]" in p for p in packets)

    solo_packets = emit_node_status("SOLO_EXPERT", "solo_expert_node")
    assert not any("[[[STATUS:" in p for p in solo_packets)  # solo_expert_node exempts status text


def test_emit_tool_start_events():
    # execute_audit_sql with column parsing
    inputs = {
        "sql": "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql",
        "db_type": "clickhouse",
        "table_name": "fqz_gz_jzsj_all_ql"
    }
    packets = emit_tool_start_events("execute_audit_sql", inputs)
    assert any("[[[MOVE:default.fqz_gz_jzsj_all_ql]]]" in p for p in packets)
    assert any("[[[SQL:SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql]]]" in p for p in packets)
    assert any("[[[BOOKSHELF:default.fqz_gz_jzsj_all_ql:psn_no,medfee_sumamt]]]" in p for p in packets)

    # calculator
    calc_packets = emit_tool_start_events("calculator", {})
    assert any("[[[MOVE:logic_core]]]" in p for p in calc_packets)


def test_format_resource_telemetry():
    usage = {"prompt_tokens": 1000, "completion_tokens": 2000}
    res = format_resource_telemetry(usage, "auditor_node")
    assert res is not None
    assert "[[[RESOURCE:" in res
    assert "'role': 'auditor_node'" in res
    assert "'prompt': 1000" in res
    assert "'completion': 2000" in res
    assert "'cost': 0.0700" in res

    assert format_resource_telemetry({}, "node") is None
    assert format_resource_telemetry(None, "node") is None


def test_format_tool_trace_packet():
    # Matched audit tool
    trace = format_tool_trace_packet("execute_audit_sql", "Rows: 10, Columns: 5")
    assert trace is not None
    assert ":::sql_trace" in trace
    assert "-- [物理取证执行] 工具: execute_audit_sql" in trace
    assert "Rows: 10, Columns: 5" in trace

    # Unmatched tool returns None
    assert format_tool_trace_packet("unrelated_tool", "data") is None


def test_render_human_review_card():
    # 1. With help request
    vals1 = {"error_log": "MODEL_REQUEST_HELP: 诊断与报销科目存在双向模糊，请指示按门诊还是住院核算"}
    card1 = render_human_review_card(vals1)
    assert "专家业务校准请求" in card1
    assert "诊断与报销科目存在双向模糊" in card1
    assert "下一步指引" in card1

    # 2. Without specific help request
    card2 = render_human_review_card({})
    assert "审计链路中断" in card2
    assert "模型由于逻辑过于复杂请求人工接管" in card2


def test_classify_and_render_error():
    tracker = MagicMock()
    tracker.stats.daily_usage = {"qwen-plus": 50000}
    model_mgr = MagicMock()
    bg_tasks = MagicMock()

    # 403 quota
    err_403 = classify_and_render_error(
        err_msg="Error 403 Forbidden: quota exhausted",
        resolved_id="qwen-plus",
        usage_tracker=tracker,
        model_manager=model_mgr,
        background_tasks=bg_tasks,
    )
    assert len(err_403) > 0
    assert any("算力配额熔断 (403)" in p or "算力配额冲突" in p for p in err_403)
    tracker.blacklist_model.assert_called_once()
