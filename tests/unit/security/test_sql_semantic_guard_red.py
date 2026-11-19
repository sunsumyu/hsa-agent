import pytest

def test_guard_sql_empty():
    from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
    res = guard_sql_semantics(state={}, sql="")
    assert res["passed"] is False
    assert "SQL为空" in res["error"]

def test_guard_sql_ranking_baseline_warning():
    from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
    state = {"original_question": "查询住院总费用最高的前10名患者"}
    sql = "SELECT psn_no, quantile(0.9)(det_item_fee_sumamt) FROM fqz_fymx_test"
    res = guard_sql_semantics(state=state, sql=sql)
    assert res["passed"] is True
    assert any("基线计算步骤" in w for w in res["warnings"])

def test_guard_sql_forbid_raw_limit():
    from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
    # 药贩子套现频繁购药原型 forbid_raw_limit=True
    state = {"original_question": "排查药贩子频繁倒药套现行为"}
    sql = "SELECT * FROM fqz_fymx_test WHERE setl_id = '123' LIMIT 10"
    res = guard_sql_semantics(state=state, sql=sql)
    assert res["passed"] is False
    assert "严禁对明细流水直接施加 LIMIT 采样" in res["error"] or "GROUP BY" in res["error"]

def test_guard_sql_pure_schema_probe_allow():
    from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
    state = {"original_question": "排查分解住院违规行为"}
    # 纯结构探查 SELECT * FROM tbl LIMIT 5
    sql = "SELECT * FROM fqz_fymx_test LIMIT 5"
    res = guard_sql_semantics(state=state, sql=sql)
    assert res["passed"] is True
    assert res["error"] is None

def test_guard_sql_normal_pass():
    from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
    state = {"original_question": "统计各医院男性结算妇科专属药品的总金额"}
    sql = "SELECT fixmedins_name, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = '1' GROUP BY fixmedins_name"
    res = guard_sql_semantics(state=state, sql=sql)
    assert res["passed"] is True
    assert res["error"] is None
