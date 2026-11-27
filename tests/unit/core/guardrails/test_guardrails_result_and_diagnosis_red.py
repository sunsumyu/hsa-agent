import pytest
from app.core.guardrails.guardrail_result import GuardrailResult
from app.core.guardrails.diagnostic_interpreter import DiagnosticInterpreter
from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
from app.core.guardrails.result_matching_guard import guard_result_matching


def test_guardrail_result_dict_contract():
    """测试 GuardrailResult 兼容字典契约与属性契约"""
    res = GuardrailResult(
        passed=False,
        error="测试拦截错误",
        warnings=["警告1"],
        diagnostic_hint="请修正查询参数",
    )
    # 属性访问
    assert res.passed is False
    assert res.error == "测试拦截错误"
    assert res.warnings == ["警告1"]
    assert res.diagnostic_hint == "请修正查询参数"

    # 字典下角标访问兼容
    assert res["passed"] is False
    assert res["error"] == "测试拦截错误"
    assert res["warnings"] == ["警告1"]
    assert res["diagnostic_hint"] == "请修正查询参数"

    # get 方法
    assert res.get("passed") is False
    assert res.get("non_exist", "default") == "default"
    assert res.get("diagnostic_hint") == "请修正查询参数"

    # to_dict 方法
    d = res.to_dict()
    assert isinstance(d, dict)
    assert d["passed"] is False
    assert d["diagnostic_hint"] == "请修正查询参数"


def test_gate1_intent_alignment_returns_standard_result():
    """Gate 1: 校验返回 GuardrailResult 且失败时注入 diagnostic_hint"""
    state_fail = {
        "original_question": "查询住院总费用最高的前10名患者",
        "methodology": "先计算分位数基线阈值，然后筛选大于阈值的记录",
    }
    res = guard_intent_alignment(state_fail)
    assert isinstance(res, GuardrailResult)
    assert res.passed is False
    assert res.error is not None
    assert isinstance(res.warnings, list)
    assert res.diagnostic_hint is not None
    assert "排名" in res.diagnostic_hint or "基线" in res.diagnostic_hint

    # 正常通过情况
    state_pass = {
        "original_question": "统计各定点医院男性使用妇科专属药品的结算金额",
        "methodology": "根据性别限制条件筛选，按医院维度聚合统计总金额",
    }
    res_pass = guard_intent_alignment(state_pass)
    assert isinstance(res_pass, GuardrailResult)
    assert res_pass.passed is True
    assert res_pass.error is None
    assert res_pass.diagnostic_hint is None


def test_gate2_sql_semantic_returns_standard_result_and_diagnostics():
    """Gate 2: 校验返回 GuardrailResult 且不同违规注入针对性诊断提示"""
    # 场景 1: 原型抽样违规拦截
    state = {
        "original_question": "帮我汇总一下2024年医保就诊结算的总体情况，做个资金对账。"
    }
    bad_sql = "SELECT setl_id, medfee_sumamt FROM fqz_gz_jzsj_all_ql LIMIT 10"
    res = guard_sql_semantics(state, bad_sql)
    assert isinstance(res, GuardrailResult)
    assert res.passed is False
    assert res.error is not None
    assert res.diagnostic_hint is not None
    assert "GROUP BY" in res.diagnostic_hint or "聚合" in res.diagnostic_hint

    # 场景 2: 静态恒假互斥谓词拦截
    contradictory_sql = "SELECT * FROM fqz_fymx_test WHERE gend = '1' AND gend = '2'"
    res_c = guard_sql_semantics(state, contradictory_sql)
    assert isinstance(res_c, GuardrailResult)
    assert res_c.passed is False
    assert "恒假" in res_c.error or "互斥" in res_c.error
    assert res_c.diagnostic_hint is not None
    assert "矛盾" in res_c.diagnostic_hint or "互斥" in res_c.diagnostic_hint

    # 场景 3: 排名带基线 warning
    rank_state = {"original_question": "查询最高费用前5名"}
    warn_sql = "SELECT setl_id, quantile(0.95)(medfee_sumamt) FROM fqz_gz_jzsj_all_ql"
    res_w = guard_sql_semantics(rank_state, warn_sql)
    assert isinstance(res_w, GuardrailResult)
    assert res_w.passed is True
    assert len(res_w.warnings) > 0
    assert res_w.diagnostic_hint is not None  # 针对警告提供优化提示


def test_gate3_result_matching_returns_standard_result():
    """Gate 3: 校验结果匹配守卫统一返回 GuardrailResult"""
    # None 结果警示
    res_none = guard_result_matching({"raw_data": None})
    assert isinstance(res_none, GuardrailResult)
    assert res_none.passed is True
    assert len(res_none.warnings) > 0
    assert res_none.diagnostic_hint is not None
    assert "None" in res_none.warnings[0] or "执行失败" in res_none.warnings[0]

    # 正常空列表放行
    res_empty = guard_result_matching({"raw_data": []})
    assert isinstance(res_empty, GuardrailResult)
    assert res_empty.passed is True
    assert res_empty.error is None
