import pytest
from pydantic import ValidationError
from app.multi_agent.contracts import ExecutionTier, ReviewVerdictArtifact
from app.multi_agent.tier_classifier import classify_execution_plan


def test_l0_fast_route_and_synthesis_bypass():
    assert classify_execution_plan("x", {"fast_route_id": "GENDER_CONFLICT"}).tier == ExecutionTier.L0_FAST
    assert classify_execution_plan("x", {"synthesis_done": True}).tier == ExecutionTier.L0_FAST


def test_review_verdict_artifact_enforces_risk_level_literal():
    with pytest.raises(ValidationError):
        ReviewVerdictArtifact(risk_level="超高")


def test_routine_single_point_sql_routes_to_l1():
    plan = classify_execution_plan("请核查医保结算明细中的异常退费与冲正流水总笔数")
    assert plan.tier == ExecutionTier.L1_SOLO_SQL
    assert plan.requires_graph is False


def test_fraud_ring_shared_phone_routes_to_l2_with_graph():
    plan = classify_execution_plan("排查是否存在多个参保人共用手机号的团伙骗保行为，并汇总涉案结算金额")
    assert plan.tier == ExecutionTier.L2_MULTI_AGENT
    assert plan.requires_graph is True
    assert plan.requires_policy_review is True


def test_comprehensive_multi_dimension_sweep_routes_to_l2_parallel_subtasks():
    q = "对全市定点医院做一次全面综合飞检体检，同时排查男性妇科用药、宫内节育器欺诈、异常退费与千元大额离群"
    plan = classify_execution_plan(q)
    assert plan.tier == ExecutionTier.L2_MULTI_AGENT
    assert len(plan.subtasks) >= 3


def test_clinical_exemption_review_query_routes_to_l2_policy_reviewer():
    q = "核查男性患者开具雌二醇等妇科药的违规记录，并结合临床合理性与医保法规剔除前列腺肿瘤等合规适应症"
    plan = classify_execution_plan(q)
    assert plan.tier == ExecutionTier.L2_MULTI_AGENT
    assert plan.requires_policy_review is True
