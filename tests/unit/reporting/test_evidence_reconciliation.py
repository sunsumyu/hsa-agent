"""
tests/unit/reporting/test_evidence_reconciliation.py
====================================================
[证据对账] Reporter 双源交叉核对回归测试。

契约：
1. 解析实得行数 < 通道记录行数 → 返回含丢失行数的告警消息（人工复核建议）；
2. 一致 → None；通道计数缺失（旧会话兼容）→ None；
3. 与 sanitizer 真实解析串联验证（模拟通道级丢失场景）。
"""
import pytest

from app.reporting.reporter_node_orchestrator import reconcile_evidence_counts


def test_mismatch_returns_warning_with_lost_count():
    msg = reconcile_evidence_counts(2, 3)
    assert msg is not None
    assert "丢失 1 行" in msg
    assert "人工复核" in msg


def test_consistent_counts_return_none():
    assert reconcile_evidence_counts(3, 3) is None


def test_missing_channel_count_returns_none_legacy_safe():
    # 旧会话/旁路场景无通道计数 → 不误报
    assert reconcile_evidence_counts(2, None) is None


def test_parsed_more_than_carried_returns_none():
    # 解析不可能无中生有; 超出按陈旧计数处理, 不告警
    assert reconcile_evidence_counts(5, 3) is None


def test_reconcile_with_real_sanitizer_loss_scenario():
    # 串联真实解析器: 通道计数 3 行, raw_data 被外部裁剪后仅剩 2 行可解析 → 必须告警
    from app.data.raw_data_sanitizer import RawDataSanitizer

    rows = RawDataSanitizer.sanitize_and_parse("[{'id': 1}, {'id': 2}]")
    msg = reconcile_evidence_counts(len(rows), 3)
    assert msg is not None and "丢失 1 行" in msg
