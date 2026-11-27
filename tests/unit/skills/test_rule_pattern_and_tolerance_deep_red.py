"""
tests/unit/skills/test_rule_pattern_and_tolerance_deep_red.py
============================================================
[Matt Pocock Deep Module Red Test] 规则消解器与容差策略矩阵解耦架构审计
"""

import pytest
from app.skills.rules.rule_pattern_resolver import RulePatternResolver
from app.skills.rules.rule_tolerance_policy import RuleTolerancePolicy
from app.skills.rules.rule_catalog import RuleCatalog


def test_rule_pattern_resolver_resolution_and_lookup():
    """验证规则模式消解器精准识别与反查能力"""
    resolver = RulePatternResolver()

    # 1. 核心别名解析
    assert resolver.resolve("性别矛盾") == "GENDER_CONFLICT"
    assert resolver.resolve("分解住院核查") == "DECOMPOSITION_HOSPITALIZATION"
    assert resolver.resolve("离群点检测") == "STATISTICAL_OUTLIER_DETECTOR"
    assert resolver.resolve("UNMATCHED_CUSTOM") == "UNMATCHED_CUSTOM"

    # 2. 反查别名列表
    gender_aliases = resolver.get_aliases_for_target("GENDER_CONFLICT")
    assert "GENDER" in gender_aliases
    assert "性别" in gender_aliases

    # 3. 动态扩展模式
    resolver.register_pattern("CUSTOM_PREFIX", "SPECIAL_AUDIT_TARGET")
    assert resolver.resolve("存在CUSTOM_PREFIX违规") == "SPECIAL_AUDIT_TARGET"


def test_rule_tolerance_policy():
    """验证明细容差与大容量扫描阈值决策矩阵"""
    policy = RuleTolerancePolicy()

    # 大容量明细对撞
    assert policy.compute_tolerance("GENDER_CONFLICT") == 50000
    assert policy.compute_tolerance("REPEAT_BILLING_DETECTOR") == 50000

    # 常规业务扫描
    assert policy.compute_tolerance("HIGH_FREQ_DRUG_PURCHASE") == 1000
    assert policy.compute_tolerance("CROSS_HOSPITAL_OVERLAP") == 1000

    # 支持动态覆盖
    policy.set_custom_tolerance("CUSTOM_TARGET", 25000)
    assert policy.compute_tolerance("CUSTOM_TARGET") == 25000


def test_rule_catalog_facade_delegation():
    """验证 RuleCatalog 门面透明委托与向后兼容"""
    catalog = RuleCatalog()
    assert catalog.resolve_target_id("性别冲突") == "GENDER_CONFLICT"
    assert catalog.get_tolerance("GENDER_CONFLICT") == 50000
    assert "性别冲突校验" in catalog.get_methodology("GENDER_CONFLICT")
