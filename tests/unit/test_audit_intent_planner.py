"""
Unit tests for AuditIntentPlanner (Plan-and-Solve 意图抽象规划器).
遵循 TDD 红绿灯模式：首步定义预期行为与边界。
"""

import pytest
from app.core.planning.audit_intent_planner import (
    AuditIntentPlanner,
    AuditIntent,
    AuditArchetype
)

def test_extract_male_intrauterine_device_exclusion():
    """测试用例 1: 男性使用宫内节育器 -> 锁定男性主体, 互斥排他原型"""
    prompt = "请查询男性参保人使用宫内节育器的违规就诊结算明细"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.target_gender == "1"
    assert "男" in intent.audit_subject
    assert "节育" in intent.violation_feature
    assert intent.archetype == AuditArchetype.EXCLUSION_MUTEX

def test_extract_female_prostate_medication_exclusion():
    """测试用例 2: 女性使用前列腺增生药物 -> 锁定女性主体, 互斥排他原型"""
    prompt = "排查女性患者使用治疗前列腺增生相关药品的医保基金违规使用情况"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.target_gender == "2"
    assert "女" in intent.audit_subject
    assert "前列腺" in intent.violation_feature
    assert intent.archetype == AuditArchetype.EXCLUSION_MUTEX

def test_extract_temporal_overlap_archetype():
    """测试用例 3: 异地同时就诊住院 -> 时序冲突原型"""
    prompt = "审查同一参保人在相同时间段内在两家不同医院同时发生住院结算的欺诈嫌疑"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.TEMPORAL_OVERLAP

def test_extract_missing_companion_archetype():
    """测试用例 4: 无手术收取麻醉费 -> 缺失伴随项原型"""
    prompt = "检查未收取手术治疗费但直接计收全麻/局麻费用的异常明细"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.MISSING_COMPANION

def test_handles_general_refund_query():
    """测试用例 5: 常规退费明细统计 -> 常规原型"""
    prompt = "统计2024年第一季度退费明细总金额与总笔数"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.GENERAL
    assert intent.target_gender is None

def test_handles_empty_query_safely():
    """测试用例 6: 空输入优雅降级"""
    intent = AuditIntentPlanner.extract_intent("")
    assert intent.archetype == AuditArchetype.GENERAL
