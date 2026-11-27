from domains.legal.state.case_state import (
    LegalCaseState, EvidenceItem, CaseFact, SyllogismSlice, DisputeFocus, DialecticTurn
)

def test_legal_case_state_initialization():
    evidence = EvidenceItem(
        evidence_id="EVD-01",
        title="借条原件",
        evidence_type="书证",
        content_summary="张三向李四借款20万元，约定借期一年，年利率10%",
        proof_date="2023-01-01",
        amount=200000.0,
        authenticity_level="高"
    )
    fact = CaseFact(
        fact_id="FACT-01",
        narrative="张三向李四出具借条，确认借款20万元",
        fact_time="2023-01-01",
        evidence_anchors=["EVD-01"]
    )
    slice_item = SyllogismSlice(
        element_id="consensus",
        element_name="借贷合意",
        statute_basis="民法典第667条",
        is_satisfied=True,
        supporting_facts=["FACT-01"]
    )
    focus = DisputeFocus(
        focus_id="FOCUS-01",
        issue_statement="双方借贷合意是否真实成立",
        cause_of_action="民间借贷纠纷",
        governing_statutes=["民法典第667条"],
        elements=[slice_item],
        adjudication_tendency="支持原告",
        confidence_score=0.95
    )
    turn = DialecticTurn(
        turn_index=1,
        target_focus_id="FOCUS-01",
        plaintiff_stance="持有借条原件，有真实借款签名",
        defendant_defense="辩称借条系受欺诈出具",
        counter_strategy="出具签署借条时的证人证言及微信确认记录",
        required_evidence_patch=[]
    )
    state: LegalCaseState = {
        "thread_id": "case-001",
        "messages": [],
        "metadata": {"cause": "民间借贷"},
        "current_step": "ALIGNER",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [fact],
        "evidence_items": [evidence],
        "dispute_foci": [focus],
        "active_focus_id": "FOCUS-01",
        "dialectic_history": [turn],
        "final_disposition": None
    }
    assert len(state["case_facts"]) == 1
    assert state["evidence_items"][0].amount == 200000.0
    assert state["dispute_foci"][0].elements[0].is_satisfied is True
