from domains.legal.gates.usury_evaluator import UsuryEvaluator

def test_interest_under_ceiling():
    evaluator = UsuryEvaluator()
    # 约定年利率 10%，同期 1年期 LPR 为 3.45%，4倍 LPR = 13.8%
    res = evaluator.evaluate(contract_rate=0.10, lpr_benchmark=0.0345, principal=100000.0)
    assert res.is_usurious is False
    assert res.enforceable_rate == 0.10
    assert res.excess_rate == 0.0

def test_interest_exceeding_ceiling_clamped():
    evaluator = UsuryEvaluator()
    # 约定年利率 24%，LPR 3.45% -> 4倍上限 13.8%
    res = evaluator.evaluate(contract_rate=0.24, lpr_benchmark=0.0345, principal=100000.0)
    assert res.is_usurious is True
    assert res.enforceable_rate == 0.138
    assert round(res.excess_rate, 4) == 0.102
    assert "约定年利率 24.0% 超过司法解释上限 13.8%" in res.clamping_notice
