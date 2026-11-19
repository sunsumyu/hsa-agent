"""
Red unit tests for fast_route_matcher module.
Tests deep module extraction:
- extract_query_filters
- estimate_query_complexity
- match_exact
- match_fuzzy
- match_fast_route
"""

import pytest
from app.skills.fast_router import RouteType, ModelTier, DEFAULT_RULE_CONFIG
from app.skills.fast_route_matcher import (
    extract_query_filters,
    estimate_query_complexity,
    match_exact,
    match_fuzzy,
    match_fast_route,
)


class TestFastRouteMatcher:
    def test_extract_query_filters_tail_and_amt(self):
        filters = extract_query_filters("排查共用电话 尾号 8888 以及重复收费 金额>5000")
        assert filters.get("tel") == "LIKE '%8888'"
        assert filters.get("medfee_sumamt") == "> 5000"

    def test_extract_query_filters_none(self):
        filters = extract_query_filters("排查男性妇科诊断")
        assert filters == {}

    def test_estimate_query_complexity_light(self):
        tier = estimate_query_complexity("请查一下这个多少钱")
        assert tier == ModelTier.LIGHT

    def test_estimate_query_complexity_heavy(self):
        tier = estimate_query_complexity("分析各科室的费用分布趋势和关联特征")
        assert tier == ModelTier.HEAVY

    def test_match_exact_found(self):
        res = match_exact("检查是否存在性别冲突", DEFAULT_RULE_CONFIG)
        assert res is not None
        assert res.route_type == RouteType.KNOWN_RULE
        assert res.target_id == "GENDER_CONFLICT"
        assert res.confidence == 1.0

    def test_match_fuzzy_found(self):
        res = match_fuzzy("有没有男性去妇科看病的情况", DEFAULT_RULE_CONFIG)
        assert res is not None
        assert res.route_type == RouteType.KNOWN_RULE
        assert res.target_id == "GENDER_CONFLICT"
        assert 0.7 <= res.confidence < 1.0

    def test_match_fast_route_full_pipeline(self):
        # Empty query
        res_empty = match_fast_route("", DEFAULT_RULE_CONFIG)
        assert res_empty.route_type == RouteType.UNKNOWN
        assert res_empty.confidence == 0.0

        # Exact match
        res_exact = match_fast_route("核查重复住院情况", DEFAULT_RULE_CONFIG)
        assert res_exact.route_type == RouteType.KNOWN_RULE
        assert res_exact.target_id == "CROSS_HOSPITAL_OVERLAP"
        assert res_exact.confidence == 1.0

        # Unknown fallback with complexity
        res_unknown = match_fast_route("这个月天气怎么样", DEFAULT_RULE_CONFIG)
        assert res_unknown.route_type == RouteType.UNKNOWN
        assert res_unknown.confidence == 0.0
