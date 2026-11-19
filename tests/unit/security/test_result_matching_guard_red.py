import pytest

def test_guard_result_none_warning():
    from app.core.guardrails.result_matching_guard import guard_result_matching
    state = {"raw_data": None}
    res = guard_result_matching(state)
    assert res["passed"] is True
    assert any("可能SQL执行失败" in w for w in res["warnings"])

def test_guard_result_empty_list():
    from app.core.guardrails.result_matching_guard import guard_result_matching
    state = {"raw_data": []}
    res = guard_result_matching(state)
    assert res["passed"] is True
    assert res["error"] is None

def test_guard_result_with_data():
    from app.core.guardrails.result_matching_guard import guard_result_matching
    state = {"raw_data": [{"count": 10}]}
    res = guard_result_matching(state)
    assert res["passed"] is True
    assert res["error"] is None
    assert len(res["warnings"]) == 0

def test_guard_result_invalid_state_fallback():
    from app.core.guardrails.result_matching_guard import guard_result_matching
    res = guard_result_matching(None)
    assert res["passed"] is True
