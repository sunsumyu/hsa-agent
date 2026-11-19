"""
Red test for app/memory/tool_protocol_guard.py
Testing deep module extraction of Tool Call Protocol pairing, compactor, and past turn pruning.
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.memory.tool_protocol_guard import (
    ensure_tool_pairing,
    prune_past_turn_tools,
    compress_tool_content,
)


class TestToolProtocolGuardDeepModule:
    def test_orphan_tool_message_removed(self):
        # ToolMessage with no preceding AIMessage tool_calls
        orphan = ToolMessage(content="Result without AI", tool_call_id="fake_tc_123")
        result = ensure_tool_pairing([orphan])
        assert len(result) == 0

    def test_valid_tool_pairing_preserved(self):
        ai = AIMessage(content="call", tool_calls=[{"name": "sql", "args": {}, "id": "tc1"}])
        tool = ToolMessage(content="data", tool_call_id="tc1")
        result = ensure_tool_pairing([ai, tool])
        assert len(result) == 2
        assert result[0] == ai
        assert result[1] == tool

    def test_past_turn_tools_pruned_and_active_preserved(self):
        # Turn 1: Completed turn
        h1 = HumanMessage(content="Q1")
        ai1_tc = AIMessage(content="Calling sql", tool_calls=[{"name": "sql", "args": {}, "id": "tc1"}])
        t1 = ToolMessage(content="Result 1", tool_call_id="tc1")
        ai1_final = AIMessage(content="Conclusion 1")
        
        # Turn 2: Active turn with executing tools
        h2 = HumanMessage(content="Q2")
        ai2_tc = AIMessage(content="Calling sql 2", tool_calls=[{"name": "sql", "args": {}, "id": "tc2"}])
        t2 = ToolMessage(content="Result 2", tool_call_id="tc2")

        msgs = [h1, ai1_tc, t1, ai1_final, h2, ai2_tc, t2]
        pruned = prune_past_turn_tools(msgs)

        assert h1 in pruned
        assert ai1_tc not in pruned
        assert t1 not in pruned
        assert ai1_final in pruned
        assert h2 in pruned
        assert ai2_tc in pruned
        assert t2 in pruned
        assert len(pruned) == 5

    def test_compress_large_tool_content(self):
        large_json = '{"status": "success", "message": "query ok", "records_sample": [{"medfee_sumamt": 100.0, "psn_no": "P1"}]}' + " " * 400
        tool = ToolMessage(content=large_json, tool_call_id="tc_comp")
        compressed = compress_tool_content([tool])
        assert len(compressed) == 1
        assert "工具执行摘要" in compressed[0].content
        assert compressed[0].additional_kwargs.get("_raw_content") is not None
