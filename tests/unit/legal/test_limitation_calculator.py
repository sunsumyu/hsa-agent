from domains.legal.gates.limitation_calculator import LimitationCalculator

def test_limitation_not_expired():
    calc = LimitationCalculator()
    # 到期日 2022-01-01，起诉日 2024-01-01，跨度 2 年 <= 3 年
    res = calc.evaluate(due_date="2022-01-01", demand_dates=[], filing_date="2024-01-01")
    assert res.is_expired is False
    assert res.years_elapsed == 2.0

def test_limitation_expired_without_demand():
    calc = LimitationCalculator()
    # 到期日 2019-01-01，无催收，起诉日 2023-01-01，跨度 4 年 > 3 年
    res = calc.evaluate(due_date="2019-01-01", demand_dates=[], filing_date="2023-01-01")
    assert res.is_expired is True
    assert "诉讼时效已届满" in res.warning

def test_limitation_interrupted_by_demand():
    calc = LimitationCalculator()
    # 到期日 2019-01-01，中间催收 2021-06-01，起诉日 2023-01-01 (催收到起诉未超3年)
    res = calc.evaluate(due_date="2019-01-01", demand_dates=["2021-06-01"], filing_date="2023-01-01")
    assert res.is_expired is False
    assert res.interrupted_at == "2021-06-01"
