"""
Unit tests for AuditReflectionEngine (Evaluator-Optimizer 自愈反思器).
遵循 TDD 红绿灯模式：首步定义预期行为与边界。
"""

import pytest
from app.core.planning.audit_intent_planner import AuditIntent, AuditArchetype
from app.core.reflection.audit_reflection_engine import (
    AuditReflectionEngine,
    ReflectionResult
)

def test_reflects_on_zero_hits_with_exclusion_archetype():
    """测试用例 1: 互斥场景执行结果为 0 行，且包含潜在排除错误 -> 触发反思自愈"""
    intent = AuditIntent(
        audit_subject="男性参保人",
        violation_feature="宫内节育器",
        archetype=AuditArchetype.EXCLUSION_MUTEX,
        target_gender="1"
    )
    sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%节育%' AND gend NOT LIKE '1%'"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=0,
        intent=intent
    )
    
    assert result.needs_retry is True
    assert result.diagnostic_feedback is not None
    assert "0" in result.diagnostic_feedback
    assert "男性" in result.diagnostic_feedback or "排除" in result.diagnostic_feedback
    assert "正向" in result.diagnostic_feedback or "gend LIKE '1%'" in (result.suggested_correction or "")

def test_reflects_on_static_contradiction_error():
    """测试用例 2: 捕获到静态 AST 恒假矛盾拦截 -> 产出精准反思诊断"""
    intent = AuditIntent(
        audit_subject="男性参保人",
        violation_feature="宫内节育器",
        archetype=AuditArchetype.EXCLUSION_MUTEX,
        target_gender="1"
    )
    sql = "SELECT setl_id FROM fqz_fymx_test WHERE gend NOT LIKE '1%' AND gend NOT LIKE '2%'"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=0,
        intent=intent,
        error_msg="【静态语义恒假拦截】字段 gend 产生恒假矛盾！"
    )
    
    assert result.needs_retry is True
    assert result.diagnostic_feedback is not None
    assert "恒假" in result.diagnostic_feedback

def test_passes_when_valid_results_found():
    """测试用例 3: 查询正常查出 7 笔违规明细 -> 无需重试，顺利放行"""
    intent = AuditIntent(
        audit_subject="男性参保人",
        violation_feature="宫内节育器",
        archetype=AuditArchetype.EXCLUSION_MUTEX,
        target_gender="1"
    )
    sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%节育%' AND gend LIKE '1%'"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=7,
        intent=intent
    )
    
    assert result.needs_retry is False
    assert result.diagnostic_feedback is None

def test_passes_general_query_zero_hits():
    """测试用例 4: 常规合规场景零发现 (0 笔) -> 正常业务事实，不盲目报错重试"""
    intent = AuditIntent(
        audit_subject="合规检查",
        violation_feature="常规违规筛查",
        archetype=AuditArchetype.GENERAL
    )
    sql = "SELECT setl_id FROM fqz_fymx_test WHERE det_item_fee_sumamt < -999999"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=0,
        intent=intent
    )
    
    assert result.needs_retry is False

def test_reflects_on_zero_hits_with_reversal_refund_missing_negative_filter():
    """测试用例 5 (QA-SCOPE-03): 退费原型执行 0 行且缺少负数条件 -> 触发自愈诊断"""
    intent = AuditIntent(
        audit_subject="退费与冲正结算记录",
        violation_feature="负数金额",
        archetype=AuditArchetype.REVERSAL_REFUND
    )
    sql = "SELECT setl_id FROM fqz_fymx_test WHERE det_item_fee_sumamt > 0"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=0,
        intent=intent
    )
    
    assert result.needs_retry is True
    assert "det_item_fee_sumamt < 0" in (result.suggested_correction or "") or "负数" in (result.diagnostic_feedback or "")

def test_passes_zero_findings_baseline_without_retry():
    """测试用例 6 (QA-SCOPE-06): 零发现合规基线返回 0 行 -> 正常放行，严禁死循环重试"""
    intent = AuditIntent(
        audit_subject="同日同人同院结算记录",
        violation_feature="拆单排查",
        archetype=AuditArchetype.ZERO_FINDINGS_BASELINE
    )
    sql = "SELECT psn_no FROM fqz_gz_jzsj_all_ql GROUP BY psn_no, toDate(setl_time), fixmedins_name HAVING count(DISTINCT setl_id) > 1"
    
    result = AuditReflectionEngine.evaluate_execution(
        sql=sql,
        row_count=0,
        intent=intent
    )
    
    assert result.needs_retry is False

