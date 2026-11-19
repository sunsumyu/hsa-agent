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
