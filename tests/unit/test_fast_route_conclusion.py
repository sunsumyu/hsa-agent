"""
Unit tests for fast-route conclusion template generation.
No LLM, no network — pure template logic.
"""

import pytest
from app.reporting.fast_route_conclusion import (
    generate_fast_route_conclusion,
    _extract_amount,
    _extract_psn,
    _extract_hospital,
    _extract_violation_item,
)


def test_zero_records_conclusion():
    result = generate_fast_route_conclusion([], 0.0, 0, "测试审计")
    assert "0 条" in result
    assert "未发现" in result


def test_with_records_conclusion():
    rows = [
        {"psn_no": "P001", "fixmedins_name": "市一医院", "det_item_fee_sumamt": 500.0},
        {"psn_no": "P002", "fixmedins_name": "市二医院", "medfee_sumamt": 1200.0},
    ]
    result = generate_fast_route_conclusion(rows, 1700.0, 2, "高频购药")
    assert "P001" in result
    assert "市一医院" in result
    assert "1,700.00" in result
    assert "高频购药" in result


def test_conclusion_only_samples_first_3():
    rows = [{"psn_no": f"P{i:03d}", "det_item_fee_sumamt": 100.0} for i in range(10)]
    result = generate_fast_route_conclusion(rows, 1000.0, 10, "测试")
    assert "P000" in result
    assert "P002" in result
    assert "P003" not in result


def test_extract_amount_priority():
    assert _extract_amount({"det_item_fee_sumamt": 100}) == 100.0
    assert _extract_amount({"medfee_sumamt": 50}) == 50.0
    assert _extract_amount({"amount": 30}) == 30.0
    assert _extract_amount({}) == 0.0
    assert _extract_amount({"total_fee": "abc"}) == 0.0


def test_extract_psn():
    assert _extract_psn({"psn_no": "P001"}) == "P001"
    assert _extract_psn({"PSN_NO": "P002"}) == "P002"
    assert _extract_psn({}) == "未明参保人"


def test_extract_hospital():
    assert _extract_hospital({"fixmedins_name": "市一医院"}) == "市一医院"
    assert _extract_hospital({"hospital_a": "中心医院"}) == "中心医院"
    assert _extract_hospital({}) == "未知机构"


def test_extract_violation_item_tel():
    row = {"tel": "13800001111"}
    assert "共用联系人电话" in _extract_violation_item(row, "某医院")


def test_extract_violation_item_hospital_overlap():
    row = {"hospital_b": "市二医院"}
    assert "跨机构住院重叠" in _extract_violation_item(row, "市一医院")


def test_extract_violation_item_default():
    row = {"hilist_name": "阿莫西林胶囊"}
    assert _extract_violation_item(row, "某医院") == "阿莫西林胶囊"
    assert _extract_violation_item({}, "某医院") == "限定性违规结算"
