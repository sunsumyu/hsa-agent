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


def test_labor_dispute_one_year_limitation():
    calc = LimitationCalculator()
    # 劳动争议：离职日 2023-01-01，申请仲裁日 2024-03-01，跨度 1.16 年 > 1 年
    res = calc.evaluate(
        due_date="2023-01-01",
        demand_dates=[],
        filing_date="2024-03-01",
        cause_of_action="劳动争议纠纷"
    )
    assert res.is_expired is True
    assert res.statutory_limit_years == 1.0
    assert "劳动争议调解仲裁法" in res.law_ref


def test_peremptory_period_cannot_be_interrupted():
    calc = LimitationCalculator()
    # 建设工程优先受偿权 18 个月 (1.5年)，属于除斥期间，催告不能中断
    res = calc.evaluate(
        due_date="2022-01-01",
        demand_dates=["2022-08-01"],
        filing_date="2024-01-01",  # 2年 > 1.5年
        cause_of_action="建设工程施工合同纠纷"
    )
    assert res.is_expired is True
    assert res.is_peremptory is True
    assert "除斥期间" in res.warning

