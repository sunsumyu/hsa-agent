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

    def test_missing_companion_archetype_matching(self):
        query = "核查未做手术却收取全麻费用的违规就诊明细"
        matched = archetype_registry.match_archetypes(query)
        categories = [m.category for m in matched]
        assert ArchetypeCategory.MISSING_COMPANION in categories

    def test_quality_gate_blocks_single_row_pseudo_exclusion_on_missing_companion(self):
        """单行伪排除反模式 (在单条明细记录 WHERE 直接否定伴随项目) 必须被 QualityGate 拦截"""
        state = {
            "messages": [
                ("user", "核查无手术收取麻醉费用的违规就诊结算")
            ]
        }
        # 错误反模式：单行同时过滤 麻醉 AND NOT 手术，这会导致所有麻醉明细全部误判为违规
        bad_sql = "SELECT setl_id, psn_no, hilist_name FROM fqz_fymx_test WHERE hilist_name LIKE '%麻醉%' AND hilist_name NOT LIKE '%手术%'"
        res = QualityGate.validate_sql_semantics(state, bad_sql)
        assert res["passed"] is False
        assert "伴随依赖缺失" in res["error"] or "单行伪排除" in res["error"]

    def test_quality_gate_passes_cross_row_subquery_on_missing_companion(self):
        """合规的跨行子查询 (NOT IN / NOT EXISTS) 应当被放行"""
        state = {
            "messages": [
                ("user", "核查无手术收取麻醉费用的违规就诊结算")
            ]
        }
        good_sql = (
            "SELECT setl_id, psn_no, hilist_name FROM fqz_fymx_test "
            "WHERE hilist_name LIKE '%麻醉%' "
            "AND setl_id NOT IN (SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%手术%')"
        )
        res = QualityGate.validate_sql_semantics(state, good_sql)
        assert res["passed"] is True

