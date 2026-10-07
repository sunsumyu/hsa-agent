"""
tests/unit/test_archetype_registry.py
=====================================
TDD Unit tests for TaskArchetype and ArchetypeRegistry.
Verifies domain archetype matching, invariant enforcement, and QualityGate integration.
"""

import pytest
from app.core.registry.archetype_registry import (
    ArchetypeRegistry,
    ArchetypeCategory,
    archetype_registry,
)
from app.core.context.gates import QualityGate


class TestArchetypeRegistry:
    """Test suite for ArchetypeRegistry value objects and matching logic."""

    def test_reconciliation_archetype_matching(self):
        query = "请对2024年1月的医保基金结算数据进行日结对账，检查资金是否存在差异"
        matched = archetype_registry.match_archetypes(query)
        categories = [m.category for m in matched]
        assert ArchetypeCategory.RECONCILIATION in categories
        
        recon = next(m for m in matched if m.category == ArchetypeCategory.RECONCILIATION)
        assert recon.forbid_raw_limit is True
        assert recon.requires_group_by is True
        assert "fqz_gz_jzsj_all_ql" in recon.target_tables

    def test_inventory_archetype_matching(self):
        query = "统计全国医保行政区划字典中，国家级、省级、地市级、区县级四级层级划分各有多少个？"
        matched = archetype_registry.match_archetypes(query)
        categories = [m.category for m in matched]
        assert ArchetypeCategory.INVENTORY in categories

        inv = next(m for m in matched if m.category == ArchetypeCategory.INVENTORY)
        assert inv.forbid_raw_limit is True
        assert "fqz_admdvs" in inv.target_tables

    def test_gender_conflict_archetype_matching(self):
        query = "核查是否存在男性患者使用妇科专属药品的性别限制违规行为"
        matched = archetype_registry.match_archetypes(query)
        categories = [m.category for m in matched]
        assert ArchetypeCategory.GENDER_CONFLICT in categories

        gender = next(m for m in matched if m.category == ArchetypeCategory.GENDER_CONFLICT)
        assert "fqz_fymx_test" in gender.target_tables

    def test_quality_gate_blocks_via_archetype(self):
        """QualityGate should intercept queries violating archetype invariants."""
        state = {
            "messages": [
                ("user", "核查2024年资金对账情况，计算每日结算总额与自付总额")
            ]
        }
        # Violating query: LIMIT without GROUP BY on reconciliation archetype
        sql = "SELECT setl_time, medfee_sumamt FROM fqz_gz_jzsj_all_ql LIMIT 10"
        res = QualityGate.validate_sql_semantics(state, sql)
        assert res["passed"] is False
        assert "资金对账" in res["error"] or "全量聚合统计" in res["error"]

    def test_quality_gate_passes_conformant_query(self):
        state = {
            "messages": [
                ("user", "核查2024年资金对账情况，计算每日结算总额与自付总额")
            ]
        }
        # Conformant query: with GROUP BY
        sql = "SELECT toDate(setl_time) as d, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql GROUP BY d ORDER BY d LIMIT 100"
        res = QualityGate.validate_sql_semantics(state, sql)
        assert res["passed"] is True
