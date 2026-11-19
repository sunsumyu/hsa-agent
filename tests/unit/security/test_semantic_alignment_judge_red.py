import pytest
from unittest.mock import patch, MagicMock

def test_judge_empty_inputs_pass():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    passed, msg = judge_semantic_alignment("", "")
    assert passed is True
    assert msg == ""

def test_judge_hard_rule_mismatch_fail():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    sql = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test GROUP BY psn_no"
    report = "经排查，患者所有药品的单价一致，不存在差异。"
    passed, msg = judge_semantic_alignment(sql, report)
    assert passed is False
    assert "硬规则" in msg or "单价一致" in msg

def test_judge_no_suspect_keywords_pass():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    sql = "SELECT fixmedins_name, count(*) FROM fqz_all_yy_yd GROUP BY fixmedins_name"
    report = "统计得到医疗机构总数量及分布情况。"
    passed, msg = judge_semantic_alignment(sql, report)
    assert passed is True
    assert msg == ""

def test_judge_llm_verdict_fail():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    sql = "SELECT fixmedins_name FROM fqz_all_yy_yd"
    report = "调查发现该科室存在严重多记费用行为。"
    
    fake_resp = MagicMock()
    fake_resp.content = '{"verdict": "FAIL", "reason": "科室被用于描述违规事实发现，但SQL无科室字段"}'
    
    with patch("app.core.llm_provider.LLMProvider.chat", return_value=fake_resp):
        passed, msg = judge_semantic_alignment(sql, report)
        assert passed is False
        assert "证据声明但缺 SQL 支撑" in msg

def test_judge_llm_verdict_pass():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    sql = "SELECT fixmedins_name FROM fqz_all_yy_yd"
    report = "建议对各涉事科室加强日常处方监管与合规培训。"
    
    fake_resp = MagicMock()
    fake_resp.content = '{"verdict": "PASS", "reason": "属于整改与后续行动建议"}'
    
    with patch("app.core.llm_provider.LLMProvider.chat", return_value=fake_resp):
        passed, msg = judge_semantic_alignment(sql, report)
        assert passed is True
        assert msg == ""

def test_judge_llm_crash_fallback_pass():
    from app.core.guardrails.semantic_alignment_judge import judge_semantic_alignment
    sql = "SELECT fixmedins_name FROM fqz_all_yy_yd"
    report = "调查发现某科室情况。"
    with patch("app.core.llm_provider.LLMProvider.chat", side_effect=RuntimeError("LLM Offline")):
        passed, msg = judge_semantic_alignment(sql, report)
        assert passed is True
        assert msg == ""
