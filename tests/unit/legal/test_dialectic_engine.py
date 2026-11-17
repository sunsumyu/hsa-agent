from domains.legal.agents.dialectic_arguer import DialecticArguer
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator
from domains.legal.state.case_state import DisputeFocus, DialecticTurn

def test_dialectic_arguer_generates_attack_and_defense():
    arguer = DialecticArguer()
    focus = DisputeFocus(
        focus_id="F-1",
        issue_statement="转账性质系借款还是投资往来",
        cause_of_action="民间借贷纠纷",
        adjudication_tendency="支持原告",
        confidence_score=0.7
    )
    turn = arguer.argue(focus=focus, context="被告主张转账是合作项目投资款")
    assert "原告主张" in turn.plaintiff_stance or len(turn.plaintiff_stance) > 0
    assert "投资" in turn.defendant_defense
    assert len(turn.counter_strategy) > 0

def test_judge_adjudicator_renders_opinion():
    adjudicator = JudgeAdjudicator()
    turns = [DialecticTurn(
        turn_index=1,
        target_focus_id="F-1",
        plaintiff_stance="持有转账凭证并附言借款",
        defendant_defense="抗辩系合伙投资",
        counter_strategy="查验合伙协议是否实际签署",
        required_evidence_patch=["合伙结算清册"]
    )]
    report = adjudicator.adjudicate(turns)
    assert "【法官心证评判】" in report
    assert "【原告反驳与攻防建议】" in report
