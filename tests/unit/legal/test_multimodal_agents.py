"""
tests/unit/legal/test_multimodal_agents.py
==========================================
验证民商事综合法律工作台三大非诉模块（合同审查、合同起草、诉前咨询）及其模式调度分发。
"""

import pytest
from domains.legal.agents.contract_reviewer import contract_reviewer
from domains.legal.agents.contract_drafter import contract_drafter
from domains.legal.agents.consultation_advisor import consultation_advisor
from app.api.legal_stream_coordinator import legal_stream_coordinator


def test_contract_reviewer_fallback():
    sample_contract = (
        "借款协议：甲方出借50万元给乙方，年利率约定为36%，若乙方逾期未归还，甲方有权单方扣划押金且一概不退。"
    )
    report = contract_reviewer.review_fallback(sample_contract)
    assert "## 🔍 【合同智能审查与红线排查报告】" in report
    assert "4倍LPR" in report or "LPR" in report
    assert "Redline" in report or "修订红线方案" in report
    assert "单方免责" in report or "押金" in report


def test_contract_drafter_fallback_loan():
    prompt = "请帮我起草一份借款协议，我借给张三20万元，期限1年"
    draft = contract_drafter.draft_fallback(prompt)
    assert "## 📝 【规范借款合同（借据协议）草案】" in draft
    assert "20万" in draft or "20" in draft
    assert "出借人（甲方）" in draft
    assert "4倍法定红线" in draft or "LPR" in draft
    assert "送达地址确认" in draft


def test_contract_drafter_fallback_lease():
    prompt = "帮我起草一份商业住宅房屋租赁合同"
    draft = contract_drafter.draft_fallback(prompt)
    assert "## 📝 【房屋租赁合同" in draft
    assert "租赁房屋所在地人民法院" in draft
    assert "六个月内" in draft  # 异议期


def test_contract_drafter_fallback_demand_letter():
    prompt = "请帮我写一份商事催款律师函，催促对方支付拖欠的50万货款"
    draft = contract_drafter.draft_fallback(prompt)
    assert "律师函" in draft or "催款" in draft
    assert "诉前财产保全" in draft


def test_consultation_advisor_fallback():
    prompt = "朋友借了我10万块钱快3年了，一直口头说下周还，现在微信不怎么回复了，我该怎么通过谈判和合法手段要回来？"
    advice = consultation_advisor.advise_fallback(prompt)
    assert "## 💬 【诉前协商与调解方案】" in advice
    assert "民间借贷" in advice
    assert "阶梯式谈判" in advice
    assert "司法确认" in advice
    assert "可直接复制的阶梯式沟通模版" in advice
    assert "加速到期条款" in advice


def test_coordinator_detect_mode():
    assert legal_stream_coordinator._detect_mode("【模式：合同审查】\n审查这份合同") == "contract_review"
    assert legal_stream_coordinator._detect_mode("【模式：合同起草】\n起草借条") == "contract_draft"
    assert legal_stream_coordinator._detect_mode("【模式：诉前咨询】\n如何要回欠款") == "consultation"
    assert legal_stream_coordinator._detect_mode("【模式：诉讼推演】\n开庭答辩") == "dialectic"
    assert legal_stream_coordinator._detect_mode("张三向李四借款20万元逾期未还") == "dialectic"
