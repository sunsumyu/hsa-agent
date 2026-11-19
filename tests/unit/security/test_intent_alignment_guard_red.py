import pytest
from unittest.mock import patch

def test_guard_intent_empty_info_pass():
    from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
    res = guard_intent_alignment({})
    assert res["passed"] is True
    assert res["error"] is None

def test_guard_intent_ranking_mismatch():
    from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
    state = {
        "original_question": "查询住院总费用最高的前10名患者",
        "methodology": "先计算分位数基线阈值，然后筛选大于阈值的记录",
    }
    res = guard_intent_alignment(state)
    assert res["passed"] is False
    assert res["error"] is not None

def test_guard_intent_normal_pass():
    from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
    state = {
        "original_question": "统计各定点医院男性使用妇科专属药品的结算金额",
        "methodology": "根据性别限制条件筛选，按医院维度聚合统计总金额",
    }
    res = guard_intent_alignment(state)
    assert res["passed"] is True
    assert res["error"] is None

def test_guard_intent_exception_fallback():
    from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
    state = {
        "original_question": "查询违规数据",
        "methodology": "测试方法论",
    }
    with patch("app.core.query_classifier.query_classifier.classify", side_effect=RuntimeError("Classifier Crash")):
        res = guard_intent_alignment(state)
        # 异常默认放行
        assert res["passed"] is True
        assert res["error"] is None
