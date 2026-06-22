"""
Unit tests for app/memory/message_sanitizer.py.
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.memory.message_sanitizer import (
    sanitize_for_thinking_mode,
    remove_noise,
    dedup_messages,
    trim_overflow,
    ensure_tool_pairing,
    trim_and_sanitize,
    count_message_tokens_estimate,
    _apply_pii_masking,
    sanitize_audit_content,
    mask_audit_data,
)


class TestSanitizeForThinkingMode:
    def test_human_message_preserved(self):
        msgs = [HumanMessage(content="hello")]
        result = sanitize_for_thinking_mode(msgs)
        assert len(result) == 1
        assert result[0].content == "hello"

    def test_ai_message_without_tool_calls_downgraded(self):
        msgs = [AIMessage(content="analysis result")]
        result = sanitize_for_thinking_mode(msgs)
        assert len(result) == 1
        assert result[0].__class__.__name__ == "HumanMessage"

    def test_ai_message_with_tool_calls_preserved(self):
        ai = AIMessage(content="calling tool", tool_calls=[{"name": "foo", "args": {}, "id": "1"}])
        result = sanitize_for_thinking_mode([ai])
        assert len(result) == 1
        assert result[0].__class__.__name__ == "AIMessage"

    def test_empty_ai_message_dropped(self):
        msgs = [AIMessage(content="")]
        result = sanitize_for_thinking_mode(msgs)
        assert len(result) == 0

    def test_system_message_preserved(self):
        msgs = [SystemMessage(content="system prompt")]
        result = sanitize_for_thinking_mode(msgs)
        assert len(result) == 1


class TestRemoveNoise:
    def test_empty_content_removed(self):
        msgs = [HumanMessage(content=""), HumanMessage(content="real")]
        result = remove_noise(msgs)
        assert len(result) == 1

    def test_probe_words_removed(self):
        msgs = [HumanMessage(content="ping"), HumanMessage(content="ok"), HumanMessage(content="real msg")]
        result = remove_noise(msgs)
        assert len(result) == 1

    def test_tool_message_short_kept(self):
        msgs = [ToolMessage(content="ok", tool_call_id="1")]
        result = remove_noise(msgs)
        assert len(result) == 1

    def test_real_content_preserved(self):
        msgs = [HumanMessage(content="SELECT * FROM table")]
        result = remove_noise(msgs)
        assert len(result) == 1


class TestDedupMessages:
    def test_identical_removed(self):
        m = HumanMessage(content="same")
        result = dedup_messages([m, m])
        assert len(result) == 1

    def test_different_kept(self):
        msgs = [HumanMessage(content="a"), HumanMessage(content="b")]
        result = dedup_messages(msgs)
        assert len(result) == 2


class TestTrimOverflow:
    def test_under_limit_kept(self):
        msgs = [HumanMessage(content=str(i)) for i in range(5)]
        result = trim_overflow(msgs, max_total=10)
        assert len(result) == 5

    def test_over_limit_trimmed(self):
        msgs = [HumanMessage(content=str(i)) for i in range(20)]
        result = trim_overflow(msgs, max_total=8, keep_head=2, keep_tail=4)
        assert len(result) <= 8


class TestCountMessageTokens:
    def test_empty_list_zero(self):
        assert count_message_tokens_estimate([]) == 0

    def test_english_approximate(self):
        msg = HumanMessage(content="hello world test")
        count = count_message_tokens_estimate([msg])
        assert count > 0

    def test_chinese_costs_more(self):
        en = HumanMessage(content="hello world")
        zh = HumanMessage(content="你好世界")
        assert count_message_tokens_estimate([zh]) > count_message_tokens_estimate([en])


class TestPiiMasking:
    def test_phone_masked(self):
        result = _apply_pii_masking("call 13812345678 now")
        assert "13812345678" not in result
        assert "138****5678" in result

    def test_id_card_masked(self):
        result = _apply_pii_masking("id is 310101199001011234")
        assert "310101199001011234" not in result

    def test_normal_text_preserved(self):
        text = "SELECT medfee FROM table"
        assert _apply_pii_masking(text) == text

    def test_name_after_label_masked(self):
        result = _apply_pii_masking("患者：张三")
        assert "张三" not in result


class TestMaskAuditData:
    def test_pii_fields_masked(self):
        data = [{"psn_name": "张三", "tel": "13812345678", "medfee": 100.0}]
        result = mask_audit_data(data)
        assert "13812345678" not in str(result[0]["tel"])
        assert result[0]["medfee"] == 100.0

    def test_non_pii_fields_preserved(self):
        data = [{"psn_no": "P001", "medfee": 500.0}]
        result = mask_audit_data(data)
        assert result[0]["psn_no"] == "P001"
        assert result[0]["medfee"] == 500.0

    def test_empty_list_returns_empty(self):
        assert mask_audit_data([]) == []


class TestSanitizeAuditContent:
    def test_sql_block_removed_in_non_report(self):
        msg = HumanMessage(content="here is sql:\n```sql\nSELECT 1\n```\ndone")
        result = sanitize_audit_content([msg])
        assert "SELECT 1" not in result[0].content
        assert "EXEC_TRACE_REMOVED" in result[0].content

    def test_sql_preserved_in_audit_report(self):
        report = "医保专项稽核报告\n```sql\nSELECT 1\n```"
        msg = HumanMessage(content=report)
        result = sanitize_audit_content([msg])
        assert "SELECT 1" in result[0].content


class TestTrimAndSanitize:
    def test_empty_inputs_return_empty(self):
        assert trim_and_sanitize([], []) == []

    def test_merges_left_and_right(self):
        left = [HumanMessage(content="query result one")]
        right = [HumanMessage(content="query result two")]
        result = trim_and_sanitize(left, right, max_total=10)
        assert len(result) >= 2

    def test_tuple_inputs_converted(self):
        result = trim_and_sanitize([], [("human", "test msg")], max_total=10)
        assert len(result) == 1
