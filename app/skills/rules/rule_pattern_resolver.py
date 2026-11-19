"""
app/skills/rule_pattern_resolver.py
===================================
[Matt Pocock Deep Module] 医保审计规则语义模式与别名消解器

核心职责：
1. 维护规则语义词、中英文缩写至标准 Target ID 的多源消解映射
2. 支持别名正向解析与 Target ID 反查别名列表
3. 支持运行时动态扩展注册审计新规则别名模式
"""

from __future__ import annotations

from typing import Dict, List, Tuple


class RulePatternResolver:
    """规则语义模式消解深模块"""

    DEFAULT_PATTERNS: Tuple[Tuple[str, str], ...] = (
        ("GENDER", "GENDER_CONFLICT"),
        ("性别", "GENDER_CONFLICT"),
        ("DRUG", "HIGH_FREQ_DRUG_PURCHASE"),
        ("购药", "HIGH_FREQ_DRUG_PURCHASE"),
        ("DECOMPOSITION", "DECOMPOSITION_HOSPITALIZATION"),
        ("分解", "DECOMPOSITION_HOSPITALIZATION"),
        ("CROSS", "CROSS_HOSPITAL_OVERLAP"),
        ("重复住院", "CROSS_HOSPITAL_OVERLAP"),
        ("同时", "CROSS_HOSPITAL_OVERLAP"),
        ("REPEAT_BILLING", "REPEAT_BILLING_DETECTOR"),
        ("重复收费", "REPEAT_BILLING_DETECTOR"),
        ("CONTACT_SHARING", "CONTACT_SHARING"),
        ("联系方式", "CONTACT_SHARING"),
        ("VIX", "DYNAMIC_VIX_SCAN"),
        ("变异", "DYNAMIC_VIX_SCAN"),
        ("OUTLIER", "STATISTICAL_OUTLIER_DETECTOR"),
        ("离群", "STATISTICAL_OUTLIER_DETECTOR"),
        ("CLUSTER", "FEDERATED_CLUSTER_CYPHER"),
        ("聚集", "FEDERATED_CLUSTER_CYPHER"),
        ("MAD", "ROBUST_MAD_DETECTOR"),
        ("稳健", "ROBUST_MAD_DETECTOR"),
    )

    def __init__(self):
        self._patterns: List[Tuple[str, str]] = list(self.DEFAULT_PATTERNS)

    def register_pattern(self, pattern: str, target_id: str):
        """动态注册新模式映射（置于前置高优先级）"""
        self._patterns.insert(0, (pattern.strip().upper(), target_id.strip().upper()))

    def resolve(self, rule_id: str) -> str:
        """从输入的规则语义词或英文缩写解析标准规则 Target ID"""
        key = (rule_id or "").strip().upper()
        for pattern, target in self._patterns:
            if pattern in key:
                return target
        return key

    def get_aliases_for_target(self, target_id: str) -> List[str]:
        """反查映射至特定 Target ID 的所有关键词别名"""
        target_norm = target_id.strip().upper()
        return [pattern for pattern, target in self._patterns if target == target_norm]


# 单例默认实例
rule_pattern_resolver = RulePatternResolver()
