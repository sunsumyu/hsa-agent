# tests/unit/core/observability/test_feedback_collector.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock
from app.core.observability.feedback_collector import FeedbackCollector

def test_record_feedback_accepted():
    mock_client = MagicMock()
    collector = FeedbackCollector(client=mock_client)

    ok = collector.record_auditor_feedback(
        run_id="test-run-123",
        is_accepted=True,
        feedback_category="rule_accuracy",
        comment="完全符合国家医保局38号文"
    )
    assert ok is True
    mock_client.create_feedback.assert_called_once_with(
        run_id="test-run-123",
        key="auditor_acceptance",
        score=1.0,
        value="rule_accuracy",
        comment="完全符合国家医保局38号文"
    )

def test_record_feedback_rejected():
    mock_client = MagicMock()
    collector = FeedbackCollector(client=mock_client)

    ok = collector.record_auditor_feedback(
        run_id="test-run-789",
        is_accepted=False,
        feedback_category="false_positive",
        comment="属于合理伴随用药，不应误判"
    )
    assert ok is True
    mock_client.create_feedback.assert_called_once_with(
        run_id="test-run-789",
        key="auditor_acceptance",
        score=0.0,
        value="false_positive",
        comment="属于合理伴随用药，不应误判"
    )

def test_record_feedback_graceful_on_client_none():
    collector = FeedbackCollector(client=None)
    ok = collector.record_auditor_feedback(run_id="test-run-456", is_accepted=False)
    assert ok is False # 离线环境下安全静默放行，不抛异常

def test_record_feedback_graceful_on_exception():
    mock_client = MagicMock()
    mock_client.create_feedback.side_effect = RuntimeError("Network error")
    collector = FeedbackCollector(client=mock_client)

    ok = collector.record_auditor_feedback(run_id="test-run-error", is_accepted=True)
    assert ok is False # 捕获异常，确保主业务绝对不挂
