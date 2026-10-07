"""
Unit tests for ContradictionDetector (AST 语义恒假互斥拦截器).
遵循 TDD 红绿灯模式：首步定义预期行为与边界。
"""

import pytest
from app.core.guardrails.contradiction_detector import ContradictionDetector, ContradictionViolation

def test_detects_binary_enum_exhaustive_not_exclusion():
    """测试用例 1: 二元枚举字段 gend 被同时 NOT LIKE '1%' AND NOT LIKE '2%' 导致恒假空集"""
    sql = """
    SELECT setl_id, psn_name, hilist_name, det_item_fee_sumamt 
    FROM fqz_fymx_test 
    WHERE hilist_name LIKE '%宫内节育%' 
      AND gend NOT LIKE '2%' 
      AND gend NOT LIKE '1%'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"
    assert "二元枚举" in violation.message or "恒假" in violation.message or "矛盾" in violation.message
    assert len(violation.conflicting_predicates) >= 2

def test_detects_conflicting_equality():
    """测试用例 2: 同一字段在 AND 条件下等值于不同字面量 (col = '1' AND col = '2')"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE gend = '1' AND gend = '2'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"

def test_detects_direct_negation():
    """测试用例 3: 同一字段同时出现正向等值与否定等值 (col = '1' AND col != '1')"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE gend = '1' AND gend != '1'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"

def test_passes_valid_logical_sql():
    """测试用例 4: 正常合规逻辑应当顺利通过"""
    sql = """
    SELECT setl_id, psn_name, hilist_name, det_item_fee_sumamt 
    FROM fqz_fymx_test 
    WHERE hilist_name LIKE '%宫内节育%' 
      AND (gend LIKE '1%' OR gend = '1')
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is None

def test_passes_or_conditions():
    """测试用例 5: OR 条件下的不同取值是合理的析取，不应被误判"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE gend = '1' OR gend = '2'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is None

def test_handles_empty_or_invalid_sql_gracefully():
    """测试用例 6: 空 SQL 或语法碎片不应导致崩溃"""
    assert ContradictionDetector.detect("") is None
    assert ContradictionDetector.detect("   ") is None

def test_detects_numeric_range_inversion_contradiction():
    """测试用例 7: 数值区间倒置恒假 (det_item_fee_sumamt > 1000 AND det_item_fee_sumamt < 100)"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE det_item_fee_sumamt > 1000 AND det_item_fee_sumamt < 100
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "det_item_fee_sumamt"
    assert "区间" in violation.message or "矛盾" in violation.message

def test_detects_null_contradiction():
    """测试用例 8: 空值与非空直接矛盾 (psn_no IS NULL AND psn_no IS NOT NULL)"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE psn_no IS NULL AND psn_no IS NOT NULL
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "psn_no"
    assert "空值" in violation.message or "矛盾" in violation.message

def test_detects_in_list_and_conflicting_equality():
    """测试用例 9: IN 列表与单值互斥 (gend IN ('1') AND gend = '2')"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE gend IN ('1') AND gend = '2'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"

def test_passes_valid_numeric_range():
    """测试用例 10: 正常有效区间 (det_item_fee_sumamt >= 100 AND det_item_fee_sumamt <= 1000) 应当顺利放行"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE det_item_fee_sumamt >= 100 AND det_item_fee_sumamt <= 1000
    """
    assert ContradictionDetector.detect(sql) is None

def test_detects_date_range_inversion_contradiction():
    """测试用例 11: 日期区间倒置恒假 (setl_time > '2024-12-31' AND setl_time < '2024-01-01')"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE setl_time > '2024-12-31' AND setl_time < '2024-01-01'
    """
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "setl_time"
    assert "区间" in violation.message or "矛盾" in violation.message

def test_passes_valid_date_range():
    """测试用例 12: 正常有效日期范围应当顺利放行"""
    sql = """
    SELECT * FROM fqz_fymx_test 
    WHERE setl_time >= '2024-01-01' AND setl_time <= '2024-12-31'
    """
    assert ContradictionDetector.detect(sql) is None

def test_detects_equality_violating_lower_bound():
    """测试用例 13: 数值等值与下限矛盾 (age = 10 AND age > 18)"""
    sql = "SELECT * FROM fqz_fymx_test WHERE age = 10 AND age > 18"
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "age"
    assert "矛盾" in violation.message or "下限" in violation.message or "区间" in violation.message

def test_detects_equality_violating_upper_bound():
    """测试用例 14: 数值等值与上限矛盾 (pric = 100 AND pric < 50)"""
    sql = "SELECT * FROM fqz_fymx_test WHERE pric = 100 AND pric < 50"
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "pric"
    assert "矛盾" in violation.message or "上限" in violation.message or "区间" in violation.message

def test_detects_date_equality_violating_range():
    """测试用例 15: 日期等值与日期下限矛盾 (setl_time = '2024-01-01' AND setl_time > '2024-06-01')"""
    sql = "SELECT * FROM fqz_fymx_test WHERE setl_time = '2024-01-01' AND setl_time > '2024-06-01'"
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "setl_time"
    assert "矛盾" in violation.message or "下限" in violation.message or "区间" in violation.message

def test_detects_in_list_exhausted_by_not_in():
    """测试用例 16: IN 列表被 NOT IN 集合完全覆盖排除 (gend IN ('1') AND gend NOT IN ('1', '2'))"""
    sql = "SELECT * FROM fqz_fymx_test WHERE gend IN ('1') AND gend NOT IN ('1', '2')"
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"
    assert "NOT IN" in violation.message or "排除" in violation.message or "矛盾" in violation.message

def test_detects_equality_conflicting_with_not_in():
    """测试用例 17: 等值取值命中 NOT IN 排除列表 (gend = '1' AND gend NOT IN ('1', '2'))"""
    sql = "SELECT * FROM fqz_fymx_test WHERE gend = '1' AND gend NOT IN ('1', '2')"
    violation = ContradictionDetector.detect(sql)
    assert violation is not None
    assert violation.column.lower() == "gend"
    assert "NOT IN" in violation.message or "排除" in violation.message or "矛盾" in violation.message

def test_passes_valid_equality_within_bounds():
    """测试用例 18: 合规的等值且处于有效区间内应当顺利放行"""
    sql = "SELECT * FROM fqz_fymx_test WHERE age = 25 AND age >= 18 AND age <= 60"
    assert ContradictionDetector.detect(sql) is None

def test_detects_missing_companion_pseudo_exclusion_directly():
    """测试用例 19 (Matt 深模块原则): 直接测试 ContradictionDetector 的伴随依赖缺失 AST 原型拦截"""
    from app.core.registry.archetype_registry import ArchetypeCategory, AuditArchetype
    arch = AuditArchetype(
        category=ArchetypeCategory.MISSING_COMPANION,
        name="missing_companion",
        display_name="伴随依赖缺失",
        keywords=()
    )
    bad_sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%麻醉%' AND hilist_name NOT LIKE '%手术%'"
    violation = ContradictionDetector.detect(bad_sql, archetypes=[arch])
    assert violation is not None
    assert violation.column.lower() == "hilist_name"
    assert "伴随依赖缺失" in violation.message or "单行伪排除" in violation.message

def test_passes_missing_companion_with_cross_row_directly():
    """测试用例 20: 具有跨行子查询的伴随依赖缺失查询应当直接放行"""
    from app.core.registry.archetype_registry import ArchetypeCategory, AuditArchetype
    arch = AuditArchetype(
        category=ArchetypeCategory.MISSING_COMPANION,
        name="missing_companion",
        display_name="伴随依赖缺失",
        keywords=()
    )
    good_sql = (
        "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%麻醉%' "
        "AND setl_id NOT IN (SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%手术%')"
    )
    violation = ContradictionDetector.detect(good_sql, archetypes=[arch])
    assert violation is None

def test_detects_split_billing_multiple_likes_directly():
    """测试用例 21: 直接测试 ContradictionDetector 对手术分解单行多项 LIKE 匹配的 AST 拦截"""
    from app.core.registry.archetype_registry import ArchetypeCategory, AuditArchetype
    arch = AuditArchetype(
        category=ArchetypeCategory.SPLIT_BILLING,
        name="split_billing",
        display_name="手术分解收费",
        keywords=()
    )
    bad_sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%切除术%' AND hilist_name LIKE '%引流术%'"
    violation = ContradictionDetector.detect(bad_sql, archetypes=[arch])
    assert violation is not None
    assert violation.column.lower() == "hilist_name"
    assert "分解收费" in violation.message

def test_passes_split_billing_with_join_directly():
    """测试用例 22: 自连接 JOIN 的手术分解查询应当直接放行"""
    from app.core.registry.archetype_registry import ArchetypeCategory, AuditArchetype
    arch = AuditArchetype(
        category=ArchetypeCategory.SPLIT_BILLING,
        name="split_billing",
        display_name="手术分解收费",
        keywords=()
    )
    good_sql = (
        "SELECT t1.setl_id FROM fqz_fymx_test t1 "
        "JOIN fqz_fymx_test t2 ON t1.setl_id = t2.setl_id "
        "WHERE t1.hilist_name LIKE '%切除术%' AND t2.hilist_name LIKE '%引流术%'"
    )
    violation = ContradictionDetector.detect(good_sql, archetypes=[arch])
    assert violation is None




