from domains.legal.gates.legal_logic_gate import LegalLogicGate
from domains.legal.state.case_state import LegalCaseState, EvidenceItem, CaseFact

def test_gate_rejects_loan_without_delivery_evidence():
    gate = LegalLogicGate()
    evidence = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款30万元"
    )
    # 只有借条，没有任何交付/转账证据
    state = {
        "thread_id": "c1",
        "messages": [],
        "metadata": {"cause": "民间借贷纠纷"},
        "current_step": "GATE",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [CaseFact(fact_id="F1", narrative="立有借条", evidence_anchors=["EVD-01"])],
        "evidence_items": [evidence],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None
    }
    res = gate.evaluate(state)
    assert res.passed is False
    assert res.error_code == "ERR_DELIVERY_EVIDENCE_MISSING"
    assert "款项交付凭证缺失" in res.reason

def test_gate_passes_valid_loan_case():
    gate = LegalLogicGate()
    evidence_iou = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款30万元"
    )
    evidence_transfer = EvidenceItem(
        evidence_id="EVD-02",
        title="网银转账流水凭证",
        evidence_type="电子数据",
        content_summary="招商银行网银转账30万元电子凭证"
    )
    state = {
        "thread_id": "c2",
        "messages": [],
        "metadata": {"cause": "民间借贷纠纷"},
        "current_step": "GATE",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [
            CaseFact(fact_id="F1", narrative="立有借条30万", evidence_anchors=["EVD-01"]),
            CaseFact(fact_id="F2", narrative="网银转账交付30万", evidence_anchors=["EVD-02"])
        ],
        "evidence_items": [evidence_iou, evidence_transfer],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None
    }
    res = gate.evaluate(state)
    assert res.passed is True


def test_gate_rejects_loan_with_expired_limitation_without_demand():
    gate = LegalLogicGate()
    evidence_iou = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款10万元"
    )
    evidence_transfer = EvidenceItem(
        evidence_id="EVD-02",
        title="网银转账流水凭证",
        evidence_type="电子数据",
        content_summary="交付10万元"
    )
    state = {
        "metadata": {
            "cause": "民间借贷纠纷",
            "user_question": "2021年3月借款10万借期1年，到期后一直未催告，现已逾期3年半，起诉归还本息"
        },
        "case_facts": [
            CaseFact(fact_id="F1", narrative="借期1年到期后一直未催告逾期3年半", evidence_anchors=["EVD-01"])
        ],
        "evidence_items": [evidence_iou, evidence_transfer],
    }
    res = gate.evaluate(state)
    assert res.passed is False
    assert res.error_code == "ERR_LIMITATION_EXPIRED"
    assert "诉讼时效届满" in res.reason


def test_gate_passes_loan_with_limitation_interrupted_by_wechat_evidence():
    gate = LegalLogicGate()
    evidence_iou = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款10万元"
    )
    evidence_transfer = EvidenceItem(
        evidence_id="EVD-02",
        title="网银转账流水凭证",
        evidence_type="电子数据",
        content_summary="交付10万元"
    )
    evidence_wechat = EvidenceItem(
        evidence_id="EVD-03",
        title="微信催款记录公证书",
        evidence_type="电子数据",
        content_summary="到期后微信催告还款"
    )
    state = {
        "metadata": {
            "cause": "民间借贷纠纷",
            "user_question": "2021年3月借款10万借期1年，已逾期3年半，原告出具微信催款记录公证书证明时效中断"
        },
        "case_facts": [
            CaseFact(fact_id="F1", narrative="立有借条及转账", evidence_anchors=["EVD-01", "EVD-02"]),
            CaseFact(fact_id="F2", narrative="微信催款时效中断", evidence_anchors=["EVD-03"])
        ],
        "evidence_items": [evidence_iou, evidence_transfer, evidence_wechat],
    }
    res = gate.evaluate(state)
    assert res.passed is True


def test_gate_rejects_loan_with_excessive_usurious_interest():
    gate = LegalLogicGate()
    evidence_iou = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="自然人借款10万元约定年利率36%"
    )
    evidence_transfer = EvidenceItem(
        evidence_id="EVD-02",
        title="网银转账流水凭证",
        evidence_type="电子数据",
        content_summary="交付10万元"
    )
    state = {
        "metadata": {
            "cause": "民间借贷纠纷",
            "user_question": "借条约定年利率36%，原告起诉要求归还全部本金并支持全部利息"
        },
        "case_facts": [
            CaseFact(fact_id="F1", narrative="约定年利率36%要求支持全部利息", evidence_anchors=["EVD-01", "EVD-02"])
        ],
        "evidence_items": [evidence_iou, evidence_transfer],
    }
    res = gate.evaluate(state)
    assert res.passed is False
    assert res.error_code == "ERR_USURY_EXCEEDS_CEILING"
    assert "高额利息红线门禁拦截" in res.reason

