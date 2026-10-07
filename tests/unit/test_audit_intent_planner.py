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

def test_extract_temporal_overlap_cases():
    """测试用例 11 & 12: 异地同时跨院住院与入院时间晚于出院 -> 锁定 TEMPORAL_OVERLAP 原型"""
    prompt1 = "核查是否存在同一患者在同一天内，在两家不同医院【同时住院】的情况？"
    intent1 = AuditIntentPlanner.extract_intent(prompt1)
    assert intent1.archetype == AuditArchetype.TEMPORAL_OVERLAP
    assert "时序冲突" in (intent1.enforcement_guidance or "")

    prompt2 = "核查全域医保结算是否存在入院时间晚于出院时间的异常住院结算记录"
    intent2 = AuditIntentPlanner.extract_intent(prompt2)
    assert intent2.archetype == AuditArchetype.TEMPORAL_OVERLAP
    assert "adm_time > dscg_time" in intent2.violation_feature

def test_extract_split_billing_archetype():
    """测试用例 13: 手术分解收费/拆开计费 -> 锁定 SPLIT_BILLING 原型"""
    prompt = "排查医院是否存在手术分解收费、将主干手术与子步骤拆开计费的套收行为"
    intent = AuditIntentPlanner.extract_intent(prompt)
    assert intent.archetype == AuditArchetype.SPLIT_BILLING
    assert "分解收费" in (intent.enforcement_guidance or "") or "拆分" in (intent.enforcement_guidance or "")

def test_extract_drug_resale_archetype():
    """测试用例 14: 药贩子套现/倒药闭环 -> 锁定 DRUG_RESALE 原型"""
    prompt = "排查药贩子倒药闭环套现、门诊慢特病短时间内高频次异常购药"
    intent = AuditIntentPlanner.extract_intent(prompt)
    assert intent.archetype == AuditArchetype.DRUG_RESALE
    assert "药贩子" in (intent.enforcement_guidance or "") or "GROUP BY" in (intent.enforcement_guidance or "")



