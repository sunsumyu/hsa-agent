import pytest
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator, _ROLE_CONFIG
from domains.legal.state.case_state import DialecticTurn, EvidenceItem


def test_judge_roles_config():
    assert "judge" in _ROLE_CONFIG
    assert "plaintiff" in _ROLE_CONFIG
    assert "defendant" in _ROLE_CONFIG
    assert "corporate" in _ROLE_CONFIG
    assert "citizen" in _ROLE_CONFIG


def test_judge_adjudicate_fallback_roles():
    adjudicator = JudgeAdjudicator()
    turns = [
        DialecticTurn(
            turn_index=1,
            target_focus_id="F1",
            plaintiff_stance="主张借款成立",
            defendant_defense="抗辩称系投资款",
            counter_strategy="出具银行转账附言",
            required_evidence_patch=["借条原件"],
        )
    ]

    # 原告视角
    p_text = adjudicator.adjudicate(turns, user_role="plaintiff")
    assert "原告代理律师" in p_text

    # 被告视角
    d_text = adjudicator.adjudicate(turns, user_role="defendant")
    assert "被告代理律师" in d_text

    # 企业法务视角
    c_text = adjudicator.adjudicate(turns, user_role="corporate")
    assert "企业法务总监" in c_text

    # 大众维权视角
    cit_text = adjudicator.adjudicate(turns, user_role="citizen")
    assert "当事人维权助手" in cit_text
