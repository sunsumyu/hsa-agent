from domains.legal.agents.fact_extractor import FactExtractor
from domains.legal.agents.focus_planner import FocusPlanner

def test_fact_extractor_parses_evidence_and_facts():
    extractor = FactExtractor()
    user_input = "2023年2月1日，张三在微信向李四借款10万元，转账记录显示招行转账10万元，借期半年已到期。"
    facts, evidence = extractor.extract(user_input)
    assert len(evidence) >= 1
    assert any("转账" in e.title for e in evidence)
    assert len(facts) >= 1

def test_focus_planner_generates_foci():
    planner = FocusPlanner()
    foci = planner.plan(
        cause_of_action="民间借贷纠纷",
        user_input="对方辩称转账是之前的货款，不是借款"
    )
    assert len(foci) >= 1
    assert any("借贷合意" in f.issue_statement or "交付" in f.issue_statement for f in foci)
