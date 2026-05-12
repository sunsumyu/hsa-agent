"""
tests/test_protocol_filter.py
==============================
ProtocolInterceptor 与 sanitize 的单元测试。
运行: pytest tests/test_protocol_filter.py -v
"""

import pytest
from app.protocol_filter import ProtocolInterceptor, sanitize


# ──────────────────────────────────────────────────────────────
# ProtocolInterceptor 测试
# ──────────────────────────────────────────────────────────────

class TestProtocolInterceptor:

    def test_plain_text_passthrough(self):
        """普通文本应直接透传"""
        p = ProtocolInterceptor()
        result = p.process_chunk("hello world")
        assert "".join(result) == "hello world"

    def test_internal_tag_swallowed(self):
        """内部协议标签应被吞噬"""
        p = ProtocolInterceptor()
        result = p.process_chunk("before[[[INTERNAL:data]]]after")
        joined = "".join(result)
        assert "INTERNAL" not in joined
        assert "before" in joined
        assert "after" in joined

    def test_status_tag_allowed(self):
        """STATUS 标签应允许通过"""
        p = ProtocolInterceptor()
        result = p.process_chunk("[[[STATUS:ok]]]")
        joined = "".join(result)
        assert "STATUS" in joined

    def test_audit_report_tag_allowed(self):
        """AUDIT_REPORT_V2 标签应允许通过"""
        p = ProtocolInterceptor()
        result = p.process_chunk("[[[AUDIT_REPORT_V2:data]]]")
        joined = "".join(result)
        assert "AUDIT_REPORT_V2" in joined

    def test_end_report_tag_allowed(self):
        """END_REPORT 标签应允许通过"""
        p = ProtocolInterceptor()
        result = p.process_chunk("[[[END_REPORT]]]")
        joined = "".join(result)
        assert "END_REPORT" in joined

    def test_mixed_content(self):
        """混合文本和标签"""
        p = ProtocolInterceptor()
        chunks = p.process_chunk("hello[[[STATUS:ok]]]world")
        joined = "".join(chunks)
        assert "hello" in joined
        assert "STATUS" in joined
        assert "world" in joined

    def test_flush_returns_remaining(self):
        """flush 应返回缓冲区中可能以 [ 开头但不构成标签的剩余文本"""
        p = ProtocolInterceptor()
        # "[x" 以 [ 开头但长度 ≤ 3 且不是 "[[[", 所以 process_chunk 会暂留在 buffer
        p.process_chunk("[x")
        remaining = p.flush()
        assert remaining == "[x"

    def test_flush_empty_when_inside_tag(self):
        """在标签内部时 flush 应返回空字符串"""
        p = ProtocolInterceptor()
        p.process_chunk("[[[OPEN_TAG")
        remaining = p.flush()
        assert remaining == ""

    def test_empty_input(self):
        """空输入返回空列表"""
        p = ProtocolInterceptor()
        assert p.process_chunk("") == []
        assert p.process_chunk(None) == []

    def test_buffer_overflow_protection(self):
        """超过缓冲区上限时应熔断"""
        p = ProtocolInterceptor(max_buffer_size=50)
        p.process_chunk("[[[" + "A" * 100)
        # 熔断后 is_inside_tag 重置
        assert p.is_inside_tag is False
        assert p.buffer == ""


# ──────────────────────────────────────────────────────────────
# sanitize 测试
# ──────────────────────────────────────────────────────────────

class TestSanitize:

    def test_empty_input(self):
        assert sanitize("") == ""
        assert sanitize(None) == ""

    def test_table_name_masked(self):
        """物理表名应被脱敏"""
        result = sanitize("查询 fqz_settlement_2024 表")
        assert "fqz_settlement_2024" not in result
        assert "业务稽核维度" in result

    def test_sql_keywords_masked(self):
        """SQL 关键字应被替换"""
        result = sanitize("SELECT * FROM table WHERE id = 1")
        assert "SELECT" not in result
        assert "FROM" not in result
        assert "WHERE" not in result
        assert "审计逻辑" in result

    def test_thought_tags_removed(self):
        """<thought> 标签应被移除"""
        result = sanitize("before<thought>secret thinking</thought>after")
        assert "secret thinking" not in result
        assert "before" in result
        assert "after" in result

    def test_pipe_to_newline(self):
        """|| 应转换为换行"""
        result = sanitize("line1||line2")
        assert "\n" in result

    def test_psn_fields_masked(self):
        """敏感字段名应被脱敏"""
        result = sanitize("psn_no 和 setl_id")
        assert "psn_no" not in result
        assert "setl_id" not in result

    def test_allowed_ui_tags_preserved(self):
        """StatGrid 等 UI 组件标签不应被过滤"""
        text = "<StatGrid>data</StatGrid>"
        result = sanitize(text)
        assert "StatGrid" in result

    def test_triple_bracket_internal_removed(self):
        """内部 [[[ ]]] 标签应被移除 (非白名单)"""
        result = sanitize("[[[RANDOM:hidden]]]visible")
        assert "RANDOM" not in result
        assert "visible" in result

    def test_triple_bracket_whitelist_preserved(self):
        """白名单 [[[ ]]] 标签应保留"""
        result = sanitize("[[[AUDIT_REPORT_V2:data]]]")
        assert "AUDIT_REPORT_V2" in result
