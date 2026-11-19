"""
Red test for app/reporting/row_totals_extractor.py
Testing deep module extraction of DB row set totals, aggregate column detection, and ROLLUP deconstruction.
"""
import pytest
from app.reporting.row_totals_extractor import (
    extract_db_totals,
    detect_count_column,
    detect_amount_column,
)


class TestRowTotalsExtractorDeepModule:
    def test_empty_rows_returns_zeros(self):
        cnt, amt = extract_db_totals([])
        assert cnt == 0
        assert amt == 0.0

        cnt, amt = extract_db_totals(None)
        assert cnt == 0
        assert amt == 0.0

    def test_plain_detail_rows(self):
        rows = [
            {"psn_name": "A", "det_item_fee_sumamt": 150.0},
            {"psn_name": "B", "det_item_fee_sumamt": 250.0},
        ]
        cnt, amt = extract_db_totals(rows)
        assert cnt == 2
        assert amt == 400.0

    def test_aggregate_count_column_detection(self):
        rows = [
            {"item_name": "药A", "total_records": 10, "medfee_sum": 500.0},
            {"item_name": "药B", "total_records": 20, "medfee_sum": 1000.0},
        ]
        cnt, amt = extract_db_totals(rows)
        assert cnt == 30
        assert amt == 1500.0

    def test_rollup_and_summary_row_dedup(self):
        rows = [
            {"dept": "内科", "record_count": 5, "total_amt": 500.0},
            {"dept": "外科", "record_count": 5, "total_amt": 500.0},
            {"dept": "全库总计", "record_count": 10, "total_amt": 1000.0},
        ]
        cnt, amt = extract_db_totals(rows)
        # Should prioritize summary row instead of double-counting
        assert cnt == 10
        assert amt == 1000.0

    def test_cnt_column_excluded_from_record_count(self):
        # fqz_fymx_test.cnt represents medicine quantity, NOT record count!
        first_row = {"hilist_name": "阿莫西林", "cnt": 100, "det_item_fee_sumamt": 50.0}
        detected = detect_count_column(first_row)
        assert detected is None or detected != "cnt"
