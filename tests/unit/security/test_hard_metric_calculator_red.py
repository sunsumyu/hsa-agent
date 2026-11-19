"""
Red test for app/core/guardrails/hard_metric_calculator.py
Testing deep module extraction of deterministic metric calculation, data shadow fusing, and evidence grounding.
"""
import pytest
import json

from app.core.guardrails.hard_metric_calculator import (
    calculate_hard_metrics,
    parse_table_to_rows,
    detect_anomalous_consistency,
    verify_evidence_grounding,
    DataExtractionError,
)


class TestHardMetricCalculatorDeepModule:
    def test_empty_and_null_returns_zeros(self):
        total, count, items = calculate_hard_metrics("")
        assert total == 0.0
        assert count == 0
        assert items == []

        total, count, items = calculate_hard_metrics("[]")
        assert total == 0.0
        assert count == 0

        total, count, items = calculate_hard_metrics("无查询结果")
        assert total == 0.0
        assert count == 0

    def test_dirty_data_shadow_fuses(self):
        dirty_signals = [
            "查询失败", "审计异常", "<coroutine", "object at 0x", "物理探测异常", "物理引擎执行受阻"
        ]
        for dirty in dirty_signals:
            with pytest.raises(DataExtractionError) as exc_info:
                calculate_hard_metrics(dirty)
            assert "严重状态机错误" in str(exc_info.value)

    def test_json_and_ast_parsing(self):
        raw = json.dumps([
            {"medfee": 1500.50, "psn_no": "P001"},
            {"medfee": 3000.00, "psn_no": "P002"},
        ])
        total, count, items = calculate_hard_metrics(raw)
        assert count == 2
        assert total == 4500.5
        assert len(items) == 2

    def test_markdown_and_json_table_parsing(self):
        assert parse_table_to_rows("") == []
        assert parse_table_to_rows("无查询结果") == []

        raw_md = "name | age\n--- | ---\nAlice | 30"
        rows = parse_table_to_rows(raw_md)
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"
        assert rows[0]["age"] == 30.0

    def test_cartesian_product_consistency_guard(self):
        assert detect_anomalous_consistency([]) is None
        # Exempted amounts (real clinical fraud pattern)
        exempt_rows = [{"medfee_sumamt": 5000.0} for _ in range(10)]
        assert detect_anomalous_consistency(exempt_rows) is None

        # Suspicious exploded count
        bad_rows = [{"item_count": 14848} for _ in range(10)]
        result = detect_anomalous_consistency(bad_rows)
        assert result is not None
        assert "笛卡尔积计数异常拦截" in result
        assert "14848" in result

    def test_evidence_grounding_pinning(self):
        class MockFinding:
            amount = 1200.0
            evidence = "P9999 charged"

        data = [{"medfee": 1200.0, "psn_no": "P9999"}]
        ok, msg = verify_evidence_grounding([MockFinding()], data)
        assert ok is True
        assert msg == ""

        # Hallucinated evidence
        fake_data = [{"medfee": 50.0}]
        ok, msg = verify_evidence_grounding([MockFinding()], fake_data)
        assert ok is False
        assert "证据链断裂" in msg
