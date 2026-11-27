"""
tests/unit/api/test_stream_deep_modules_red.py
=============================================
[TDD Red -> Green] 流式协议 SSE 帧封装与事件分发解耦测试：
1. StreamProtocolRenderer (3D UI 表现层协议帧生成与提取)
2. StreamCircuitBreaker (算力熔断异常分类自愈与降级文案)
3. 确保与 chat_stream.py 现有 Facade 的双向兼容性
"""

import pytest
from unittest.mock import MagicMock
from app.api.stream_protocol_renderer import StreamProtocolRenderer
from app.api.stream_circuit_breaker import StreamCircuitBreaker


def test_stream_protocol_renderer_node_status():
    renderer = StreamProtocolRenderer()
    packets = renderer.render_node_status("DATA_EXPERT", "data_expert")
    assert any("[[[STATUS:正在激活 [数据外联专家]" in p for p in packets)
    assert any("[[[MOVE:default.fqz_all_yy_yd_1]]]" in p for p in packets)


def test_stream_protocol_renderer_tool_start():
    renderer = StreamProtocolRenderer()
    inputs = {
        "sql": "SELECT psn_no, medfee_sumamt FROM fqz_all_yy_yd_1",
        "db_type": "clickhouse",
        "table_name": "archives",
    }
    packets = renderer.render_tool_start_events("execute_audit_sql", inputs)
    assert any("[[[MOVE:default.fqz_all_yy_yd_1]]]" in p for p in packets)
    assert any("[[[SQL:SELECT psn_no, medfee_sumamt FROM fqz_all_yy_yd_1]]]" in p for p in packets)
    assert any("[[[BOOKSHELF:default.fqz_all_yy_yd_1:psn_no,medfee_sumamt]]]" in p for p in packets)


def test_stream_protocol_renderer_extract_chunk():
    renderer = StreamProtocolRenderer()
    chunk_list = [
        {"type": "thought", "text": "思考中... "},
        {"type": "text", "text": "审计已完成"},
    ]
    extracted = renderer.extract_chunk_text(chunk_list)
    assert extracted == "思考中... 审计已完成"


def test_stream_circuit_breaker_handling():
    circuit_breaker = StreamCircuitBreaker()
    tracker = MagicMock()
    tracker.stats.daily_usage = {"qwen-plus": 120000}
    model_mgr = MagicMock()
    bg_tasks = MagicMock()

    # 403 限流
    res = circuit_breaker.classify_and_render(
        err_msg="Error 403 Forbidden: quota exhausted",
        resolved_id="qwen-plus",
        usage_tracker=tracker,
        model_manager=model_mgr,
        background_tasks=bg_tasks,
    )
    assert len(res) > 0
    assert any("算力配额" in p for p in res)
    tracker.blacklist_model.assert_called_once()
