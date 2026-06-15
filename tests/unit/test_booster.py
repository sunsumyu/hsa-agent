"""
Unit tests for app/core/booster.py (PrecisionBooster).
"""
import pytest
import json
from app.core.booster import PrecisionBooster, DataExtractionError


class TestCalculateHardMetrics:
    def test_empty_string_returns_zeros(self):
        total, count, items = PrecisionBooster.calculate_hard_metrics("")
        assert total == 0.0
        assert count == 0
        assert items == []

    def test_empty_list_string_returns_zeros(self):
        total, count, items = PrecisionBooster.calculate_hard_metrics("[]")
        assert total == 0.0
        assert count == 0

    def test_no_results_signal_returns_zeros(self):
        total, count, items = PrecisionBooster.calculate_hard_metrics("无查询结果")
        assert total == 0.0
        assert count == 0

    def test_dirty_data_raises_error(self):
        dirty_signals = ["查询失败", "审计异常", "<coroutine", "object at 0x"]
        for dirty in dirty_signals:
            with pytest.raises(DataExtractionError):
                PrecisionBooster.calculate_hard_metrics(dirty)

    def test_json_array_with_amounts(self):
        raw = json.dumps([
            {"medfee": 1500.50, "psn_no": "P001"},
            {"medfee": 3000.00, "psn_no": "P002"},
        ])
        total, count, items = PrecisionBooster.calculate_hard_metrics(raw)
        assert count == 2
        assert total == 4500.5
        assert len(items) == 2

    def test_json_object_wrapped(self):
        raw = json.dumps({"amount": 999.99})
        total, count, items = PrecisionBooster.calculate_hard_metrics(raw)
        assert count == 1
        assert total == 999.99

    def test_amount_with_commas(self):
        raw = json.dumps([{"medfee": "1,500.00"}])
        total, count, items = PrecisionBooster.calculate_hard_metrics(raw)
        assert total == 1500.0

    def test_id_fields_excluded_from_amount(self):
        raw = json.dumps([{"id": 99999, "medfee": 100.0}])
        total, count, items = PrecisionBooster.calculate_hard_metrics(raw)
        assert total == 100.0

    def test_evidence_items_deduplicated_and_sorted(self):
        raw = json.dumps([
            {"medfee": 500.0},
            {"medfee": 500.0},
            {"medfee": 1000.0},
        ])
        total, count, items = PrecisionBooster.calculate_hard_metrics(raw)
        assert total == 2000.0
        assert items == [1000.0, 500.0]


class TestParseTableToRows:
    def test_empty_returns_empty_list(self):
        assert PrecisionBooster.parse_table_to_rows("") == []

    def test_no_results_returns_empty(self):
        assert PrecisionBooster.parse_table_to_rows("无查询结果") == []

    def test_json_array_parsed(self):
        raw = "name | age\n--- | ---\nAlice | 30"
        rows = PrecisionBooster.parse_table_to_rows(raw)
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"


class TestDetectAnomalousConsistency:
    def test_empty_returns_none(self):
        assert PrecisionBooster.detect_anomalous_consistency([]) is None

    def test_few_rows_returns_none(self):
        rows = [{"x": 1}, {"x": 2}]
        assert PrecisionBooster.detect_anomalous_consistency(rows) is None

    def test_identical_large_values_detected(self):
        rows = [{"item_count": 14848} for _ in range(10)]
        result = PrecisionBooster.detect_anomalous_consistency(rows)
        assert result is not None
        assert "14848" in result

    def test_year_values_not_flagged(self):
        rows = [{"year": 2026} for _ in range(10)]
        assert PrecisionBooster.detect_anomalous_consistency(rows) is None

    def test_small_values_not_flagged(self):
        rows = [{"flag": 1} for _ in range(10)]
        assert PrecisionBooster.detect_anomalous_consistency(rows) is None

    def test_varied_values_not_flagged(self):
        rows = [{"v": i} for i in range(10)]
        assert PrecisionBooster.detect_anomalous_consistency(rows) is None


class TestVerifyEvidenceGrounding:
    def test_empty_findings_passes(self):
        ok, msg = PrecisionBooster.verify_evidence_grounding([], [])
        assert ok is True
        assert msg == ""

    def test_findings_without_data_fails(self):
        ok, msg = PrecisionBooster.verify_evidence_grounding(["some finding"], [])
        assert ok is False
        assert len(msg) > 0

    def test_finding_amount_in_data_passes(self):
        class MockFinding:
            amount = 1500.0
            evidence = "P001 charged"
        data = [{"medfee": 1500.0, "psn_no": "P001"}]
        ok, msg = PrecisionBooster.verify_evidence_grounding([MockFinding()], data)
        assert ok is True

    def test_finding_amount_not_in_data_fails(self):
        class MockFinding:
            amount = 99999.0
            evidence = "XYZ12345 charged"
        data = [{"medfee": 100.0}]
        ok, msg = PrecisionBooster.verify_evidence_grounding([MockFinding()], data)
        assert ok is False


class TestVerifySemanticAlignment:
    def test_aligned_passes(self):
        sql = "SELECT medfee_sumamt FROM fqz_gz_jzsj_all_ql"
        report = "金额完全相同的记录"
        ok, msg = PrecisionBooster.verify_semantic_alignment(sql, report)
        assert ok is True

    def test_hard_rule_violation_fails(self):
        sql = "SELECT psn_no FROM fqz_gz_jzsj_all_ql"
        report = "金额完全相同的记录"
        ok, msg = PrecisionBooster.verify_semantic_alignment(sql, report)
        assert ok is False

    def test_none_sql_handled(self):
        ok, msg = PrecisionBooster.verify_semantic_alignment(None, "random report")
        assert ok is True
