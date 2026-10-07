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

def test_handles_general_settlement_query():
    """测试用例 5: 常规结算业务统计 -> 常规原型"""
    prompt = "统计2024年第一季度门诊结算总金额与总人次"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.GENERAL
    assert intent.target_gender is None

def test_handles_empty_query_safely():
    """测试用例 6: 空输入优雅降级"""
    intent = AuditIntentPlanner.extract_intent("")
    assert intent.archetype == AuditArchetype.GENERAL

def test_extract_male_gynecological_drugs_scope01():
    """测试用例 7 (QA-SCOPE-01): 男性开具益母草颗粒和地屈孕酮片 -> 锁定男性主体, 互斥排他原型"""
    prompt = "排查男性参保人开具益母草颗粒和地屈孕酮片的违规结算明细"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.target_gender == "1"
    assert "男" in intent.audit_subject
    assert ("益母草" in intent.violation_feature or "地屈孕酮" in intent.violation_feature or "妇科" in intent.violation_feature)
    assert intent.archetype == AuditArchetype.EXCLUSION_MUTEX

def test_extract_reversal_refund_scope03():
    """测试用例 8 (QA-SCOPE-03): 负数冲正与退费记录核查 -> 锁定 REVERSAL_REFUND 原型"""
    prompt = "核查费用明细中的退费记录与负数冲正结算明细"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.REVERSAL_REFUND
    assert "退费" in intent.audit_subject or "冲正" in intent.audit_subject
    assert "det_item_fee_sumamt < 0" in (intent.enforcement_guidance or "")

def test_extract_zero_findings_baseline_scope06():
    """测试用例 9 (QA-SCOPE-06): 同人同日同院多次结算排查 -> 锁定 ZERO_FINDINGS_BASELINE 原型"""
    prompt = "排查同人同日同院多次结算的拆单骗保行为"
    intent = AuditIntentPlanner.extract_intent(prompt)
    
    assert intent.archetype == AuditArchetype.ZERO_FINDINGS_BASELINE
    assert "合规" in (intent.enforcement_guidance or "") or "零发现" in (intent.enforcement_guidance or "")

def test_extract_directory_inspection_scope07_08_09():
    """测试用例 10 (QA-SCOPE-07/08/09): 字典、机构资质与目录核查 -> 锁定 DIRECTORY_INSPECTION 原型"""
    prompt1 = "统计医保定点医药机构库范围与医院等级分布"
    intent1 = AuditIntentPlanner.extract_intent(prompt1)
    assert intent1.archetype == AuditArchetype.DIRECTORY_INSPECTION

    prompt2 = "穿透核查全国四级医保行政区划字典层级"
    intent2 = AuditIntentPlanner.extract_intent(prompt2)
    assert intent2.archetype == AuditArchetype.DIRECTORY_INSPECTION

    prompt3 = "核查临床药品目录中抗生素品种及生产厂家"
    intent3 = AuditIntentPlanner.extract_intent(prompt3)
    assert intent3.archetype == AuditArchetype.DIRECTORY_INSPECTION

