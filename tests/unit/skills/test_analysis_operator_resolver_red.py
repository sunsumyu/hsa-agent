"""
Red unit tests for analysis_operator_resolver deep module.
Tests:
- resolve_audit_rule_id
- resolve_anomaly_algorithm_id
- get_operator_tolerance
- validate_cypher_spatial_isolation
- extract_entity_ids
"""

import pytest
from app.skills.rules.analysis_operator_resolver import (
    resolve_audit_rule_id,
    resolve_anomaly_algorithm_id,
    get_operator_tolerance,
    validate_cypher_spatial_isolation,
    extract_entity_ids,
)


class TestAnalysisOperatorResolver:
    def test_resolve_audit_rule_id(self):
        assert resolve_audit_rule_id("GENDER") == "GENDER_CONFLICT"
        assert resolve_audit_rule_id("性别冲突排查") == "GENDER_CONFLICT"
        assert resolve_audit_rule_id("DRUG") == "HIGH_FREQ_DRUG_PURCHASE"
        assert resolve_audit_rule_id("购药频率") == "HIGH_FREQ_DRUG_PURCHASE"
        assert resolve_audit_rule_id("分解住院") == "DECOMPOSITION_HOSPITALIZATION"
        assert resolve_audit_rule_id("重复住院") == "CROSS_HOSPITAL_OVERLAP"
        assert resolve_audit_rule_id("同时住院") == "CROSS_HOSPITAL_OVERLAP"
        assert resolve_audit_rule_id("重复收费") == "REPEAT_BILLING_DETECTOR"
        assert resolve_audit_rule_id("联系方式") == "CONTACT_SHARING"
        assert resolve_audit_rule_id("CUSTOM_RULE_01") == "CUSTOM_RULE_01"

    def test_resolve_anomaly_algorithm_id(self):
        assert resolve_anomaly_algorithm_id("VIX") == "VIX_ANOMALY_SCAN"
        assert resolve_anomaly_algorithm_id("机构费用变异") == "VIX_ANOMALY_SCAN"
        assert resolve_anomaly_algorithm_id("OUTLIER") == "STATISTICAL_OUTLIER_DETECTOR"
        assert resolve_anomaly_algorithm_id("离群点") == "STATISTICAL_OUTLIER_DETECTOR"
        assert resolve_anomaly_algorithm_id("CLUSTER") == "CLUSTER_ENCOUNTER_DETECTOR"
        assert resolve_anomaly_algorithm_id("聚集") == "CLUSTER_ENCOUNTER_DETECTOR"
        assert resolve_anomaly_algorithm_id("MAD") == "ROBUST_MAD_DETECTOR"
        assert resolve_anomaly_algorithm_id("稳健") == "ROBUST_MAD_DETECTOR"
        assert resolve_anomaly_algorithm_id("CUSTOM_ALGO_02") == "CUSTOM_ALGO_02"

    def test_get_operator_tolerance(self):
        assert get_operator_tolerance("REPEAT_BILLING_DETECTOR") == 50000
        assert get_operator_tolerance("GENDER_CONFLICT") == 1000
        assert get_operator_tolerance("VIX_ANOMALY_SCAN", default=20000) == 20000

    def test_validate_cypher_spatial_isolation(self):
        # Clean cypher
        clean_cypher = "MATCH (p:Patient)-[:HAS_PHONE]->(c:Phone) RETURN p.id, c.number"
        assert validate_cypher_spatial_isolation(clean_cypher) is None

        # Violating cypher with relational table fqz_...
        bad_cypher = "MATCH (n) WHERE n.table = 'fqz_fymx_test' RETURN n"
        err = validate_cypher_spatial_isolation(bad_cypher)
        assert err is not None
        assert "fqz_fymx_test" in err

    def test_extract_entity_ids(self):
        records = [
            {"p_id": "P001", "name": "Alice"},
            {"p_id": "P002", "name": "Bob"},
            {"p_id": "P001", "name": "Alice2"},  # duplicate
            {"p_id": None},
        ]
        # Specific key
        ids = extract_entity_ids(records, return_key="p_id")
        assert set(ids) == {"P001", "P002"}

        # Fallback to first value
        records_no_key = [
            {"id": "X100", "val": 1},
            {"id": "X200", "val": 2},
        ]
        ids2 = extract_entity_ids(records_no_key)
        assert set(ids2) == {"X100", "X200"}
