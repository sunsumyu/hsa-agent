"""
Unit tests for app/reporting/policy_matcher.py.
"""
import pytest
from app.reporting.policy_matcher import (
    match_policies,
    match_oral_policy,
    match_icd_codes,
    build_zero_finding_boundary,
    match_visualization,
    build_actionable_steps,
)


class TestMatchPolicies:
    def test_default_when_no_keywords(self):
        result = match_policies("random question xyz")
        assert "735" in result

    def test_pharmacy_inventory(self):
        result = match_policies("进销存库存倒挂")
        assert "735" in result

    def test_duplicate_testing(self):
        result = match_policies("重复检查增强ct")
        assert "互认" in result

    def test_drg_dedup(self):
        result = match_policies("分解住院再次住院DRG")
        assert result.count("48号") == 1

    def test_surgery(self):
        result = match_policies("主刀医师连轴转物理极限")
        assert "18号" in result or "手术" in result

    def test_family_fraud(self):
        result = match_policies("家族套保团伙药贩子")
        assert "刑法" in result or "诈骗" in result

    def test_multiple_categories_joined(self):
        result = match_policies("进销存和重复检查")
        assert "；" in result


class TestMatchOralPolicy:
    def test_dental_returns_policy(self):
        result = match_oral_policy("检查口腔拔牙种植")
        assert len(result) > 10

    def test_non_dental_returns_empty(self):
        assert match_oral_policy("check store inventory") == ""


class TestMatchIcdCodes:
    def test_default(self):
        assert "I10-I15" in match_icd_codes("random audit xyz")

    def test_dental(self):
        assert "K02" in match_icd_codes("检查口腔拔牙")

    def test_icu(self):
        assert match_icd_codes("ICU重症") != ""

    def test_therapy(self):
        assert match_icd_codes("理疗推拿按摩") != ""


class TestBuildZeroFindingBoundary:
    def test_contains_boundary_header(self):
        result = build_zero_finding_boundary("random", 10000, "2025-01-01", "2025-06-30")
        assert len(result) > 100
        assert "10,000" in result

    def test_uses_table_info(self):
        result = build_zero_finding_boundary(
            "random", 5000, "2025-01", "2025-06", table_info="my_table"
        )
        assert "my_table" in result

    def test_default_table_name(self):
        result = build_zero_finding_boundary("random", 5, "2025-01", "2025-06")
        assert "fqz_gz_jzsj_all_ql" in result


class TestMatchVisualization:
    def test_family_fraud_positive(self):
        result = match_visualization("家族套保团伙", finding_count=3)
        assert len(result) > 50

    def test_family_fraud_zero(self):
        result = match_visualization("家族套保团伙", finding_count=0)
        assert len(result) > 50

    def test_surgeon_workload(self):
        result = match_visualization("主刀连轴转", finding_count=0)
        assert len(result) > 50

    def test_drg_revolving(self):
        result = match_visualization("DRG分解住院出院", finding_count=0)
        assert len(result) > 50

    def test_no_match_returns_empty(self):
        assert match_visualization("wuguan wenti cha shuju", finding_count=0) == ""


class TestBuildActionableSteps:
    def test_returns_actionable_content(self):
        result = build_actionable_steps()
        assert "Actionable" in result
        assert len(result) > 100
