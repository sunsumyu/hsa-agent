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
