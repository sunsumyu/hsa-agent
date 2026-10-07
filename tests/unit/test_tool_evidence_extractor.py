"""
tests/unit/test_tool_evidence_extractor.py
==========================================
TDD Unit tests for ToolEvidenceExtractor.
Verifies parsing, evidence extraction, probe isolation, and data truncation.
"""

import pytest
from app.agents.tool_evidence_extractor import ToolEvidenceExtractor, ProcessedToolResults


class TestToolEvidenceExtractor:
    """Tests for ToolEvidenceExtractor deep module."""

    def test_extract_from_dict_success(self):
        extractor = ToolEvidenceExtractor()
        tool_call = {"id": "call_1", "name": "execute_audit_sql"}
        tool_res = {
            "status": "SUCCESS",
            "sql_logic": "SELECT * FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 10000",
            "data": [{"setl_id": "1", "medfee_sumamt": 12000}],
            "methodology": "大额费用核查"
        }
        state = {"sql_history": []}
        
        results = extractor.process([(tool_call, tool_res)], state)
        assert isinstance(results, ProcessedToolResults)
        assert results.has_error is False
        assert "12000" in results.raw_data
        assert "SELECT *" in results.sql_query
        assert results.methodology == "大额费用核查"
        assert len(results.tool_msgs) == 1

    def test_extract_from_json_string(self):
        extractor = ToolEvidenceExtractor()
        tool_call = {"id": "call_2", "name": "execute_audit_sql"}
        json_str = '{"status": "SUCCESS", "sql_logic": "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = \'1\' GROUP BY psn_no", "data": "psn_1001"}'
        state = {}

        results = extractor.process([(tool_call, json_str)], state)
        assert results.has_error is False
        assert "psn_1001" in results.raw_data
        assert "GROUP BY" in results.sql_query

    def test_probe_query_data_is_excluded_from_evidence(self):
        extractor = ToolEvidenceExtractor()
        tool_call = {"id": "call_3", "name": "execute_audit_sql"}
        # A probe query like SELECT count(*)
        probe_res = {
            "status": "SUCCESS",
            "sql_logic": "SELECT count(*) FROM fqz_gz_jzsj_all_ql",
            "data": "2138354"
        }
        state = {}

        results = extractor.process([(tool_call, probe_res)], state)
        # Probe data should not contaminate the core raw_data
        assert results.raw_data == "" or "2138354" not in results.raw_data
        assert results.sql_history == ["SELECT count(*) FROM fqz_gz_jzsj_all_ql"]

    def test_truncation_safety(self):
        extractor = ToolEvidenceExtractor(max_chars=50)
        tool_call = {"id": "call_4", "name": "execute_audit_sql"}
        huge_data = "A" * 200
        tool_res = {
            "status": "SUCCESS",
            "sql_logic": "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = \'1\' GROUP BY psn_no",
            "data": huge_data
        }
        state = {}

        results = extractor.process([(tool_call, tool_res)], state)
        assert "WARNING: Data truncated" in results.raw_data
        assert len(results.raw_data.split("...")[0]) <= 50
