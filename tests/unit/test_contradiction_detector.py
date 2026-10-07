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


