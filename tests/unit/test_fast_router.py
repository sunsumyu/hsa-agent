"""
Unit tests for FastAuditRouter — routing decisions and keyword matching.

Uses DEFAULT_RULE_CONFIG directly (no YAML dependency) for deterministic
 test results.
"""

import pytest
from app.skills.fast_router import (
    FastAuditRouter,
    RouteType,
    ModelTier,
    RouteResult,
    DEFAULT_RULE_CONFIG,
)


@pytest.fixture
def router():
    """Router with hardcoded default config (no YAML dependency)."""
    return FastAuditRouter(rule_config=DEFAULT_RULE_CONFIG)


# ── Empty / edge cases ────────────────────────────────────────

class TestEdgeCases:
    def test_empty_question_returns_unknown(self, router):
        result = router.classify("")
        assert result.route_type == RouteType.UNKNOWN
        assert result.confidence == 0.0

    def test_none_question_returns_unknown(self, router):
        result = router.classify(None)
        assert result.route_type == RouteType.UNKNOWN

    def test_whitespace_only_returns_unknown(self, router):
        result = router.classify("   ")
        assert result.route_type == RouteType.UNKNOWN


# ── Exact keyword matching ────────────────────────────────────

class TestExactMatching:
    def test_gender_conflict_exact(self, router):
        result = router.classify("检查是否存在性别冲突")
        assert result.route_type == RouteType.KNOWN_RULE
        assert result.target_id == "GENDER_CONFLICT"
        assert result.confidence == 1.0

    def test_cross_hospital_overlap_exact(self, router):
        result = router.classify("核查重复住院情况")
        assert result.route_type == RouteType.KNOWN_RULE
        assert result.target_id == "CROSS_HOSPITAL_OVERLAP"

    def test_contact_sharing_exact(self, router):
        result = router.classify("检查联系方式共用")
        assert result.route_type == RouteType.KNOWN_RULE
        assert result.target_id == "CONTACT_SHARING"

    def test_vix_anomaly_exact(self, router):
        result = router.classify("扫描机构变异指数")
        assert result.route_type == RouteType.KNOWN_ALGO
        assert result.target_id == "VIX_ANOMALY_SCAN"


# ── Fuzzy keyword matching ────────────────────────────────────

class TestFuzzyMatching:
    def test_gender_fuzzy_male_gynecology(self, router):
        result = router.classify("有没有男性去妇科看病的情况")
        assert result.route_type == RouteType.KNOWN_RULE
        assert result.target_id == "GENDER_CONFLICT"
        assert result.confidence < 1.0
        assert result.confidence >= 0.7

    def test_cross_hospital_fuzzy(self, router):
        result = router.classify("有没有跨机构住院的记录")
        assert result.route_type == RouteType.KNOWN_RULE
        assert result.target_id == "CROSS_HOSPITAL_OVERLAP"

    def test_repeat_billing_fuzzy(self, router):
        result = router.classify("同一天同一患者多次收费的情况")
        assert result.route_type == RouteType.KNOWN_RULE
        assert "REPEAT_BILLING" in result.target_id


# ── Unknown type + complexity estimation ──────────────────────

class TestUnknownRouting:
    def test_unmatched_returns_unknown(self, router):
        result = router.classify("这个月天气怎么样")
        assert result.route_type == RouteType.UNKNOWN
        assert result.confidence == 0.0

    def test_complex_analysis_routes_heavy(self, router):
        result = router.classify("分析各科室的费用分布趋势和关联特征")
        assert result.route_type == RouteType.UNKNOWN
        assert result.model_tier == ModelTier.HEAVY

    def test_simple_question_routes_light(self, router):
        result = router.classify("查一下这个多少钱")
        assert result.route_type == RouteType.UNKNOWN
        assert result.model_tier == ModelTier.LIGHT

    def test_long_query_defaults_heavy(self, router):
        long_query = "请帮我核查一下在特定时间段内某区域内多家医疗机构之间可能存在的异常结算模式" * 2
        result = router.classify(long_query)
        assert result.model_tier == ModelTier.HEAVY


# ── Dynamic parameter extraction ──────────────────────────────

class TestParameterExtraction:
    def test_tail_number_extracted(self, router):
        result = router.classify("检查联系方式共用 尾号 8888")
        assert result.extra_filters.get("tel") == "LIKE '%8888'"

    def test_amount_threshold_extracted(self, router):
        result = router.classify("检查重复收费 金额>5000")
        assert result.extra_filters.get("medfee_sumamt") == "> 5000"

    def test_no_params_extracted_for_plain_query(self, router):
        result = router.classify("检查性别冲突")
        assert result.extra_filters == {}


# ── Config management ─────────────────────────────────────────

class TestConfigManagement:
    def test_get_all_rules_returns_config(self, router):
        rules = router.get_all_rules()
        assert len(rules) == len(DEFAULT_RULE_CONFIG)
        assert any(r["target_id"] == "GENDER_CONFLICT" for r in rules)

    def test_empty_config_means_pure_llm(self):
        router = FastAuditRouter(rule_config=[])
        result = router.classify("检查性别冲突")
        assert result.route_type == RouteType.UNKNOWN
