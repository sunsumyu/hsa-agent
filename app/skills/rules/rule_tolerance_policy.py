"""
app/skills/rule_tolerance_policy.py
===================================
[Matt Pocock Deep Module] 医保审计物理执行容差阈值决策矩阵

核心职责：
1. 区分明细级对撞扫描（高容差，如重复计费、性别对撞 50,000 条）与汇总统计扫描（常规容差 1,000 条）
2. 支持针对特定规则的容差动态覆盖与安全保护
"""

from __future__ import annotations

from typing import Dict


class RuleTolerancePolicy:
    """业务容差策略矩阵深模块"""

    HIGH_TOLERANCE_KEYWORDS = ("REPEAT_BILLING", "GENDER")
    DEFAULT_HIGH_TOLERANCE = 50000
    DEFAULT_NORMAL_TOLERANCE = 1000

    def __init__(self):
        self._custom_tolerances: Dict[str, int] = {}

    def set_custom_tolerance(self, target_id: str, tolerance: int):
        """设置特定规则自定义容差"""
        self._custom_tolerances[target_id.strip().upper()] = tolerance

    def compute_tolerance(self, target_id: str) -> int:
        """获取明细级业务容差阈值"""
        key = target_id.strip().upper()
        if key in self._custom_tolerances:
            return self._custom_tolerances[key]

        if any(kw in key for kw in self.HIGH_TOLERANCE_KEYWORDS):
            return self.DEFAULT_HIGH_TOLERANCE

        return self.DEFAULT_NORMAL_TOLERANCE


# 单例默认实例
rule_tolerance_policy = RuleTolerancePolicy()
