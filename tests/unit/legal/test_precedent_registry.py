import pytest
from domains.legal.registry.precedent_registry import precedent_registry, PrecedentCase


def test_precedent_registry_loaded():
    cases = precedent_registry._cases
    assert len(cases) >= 6
    causes = {c.cause_of_action for c in cases}
    assert "民间借贷纠纷" in causes
    assert "买卖合同纠纷" in causes
    assert "建设工程施工合同纠纷" in causes
    assert "劳动争议纠纷" in causes


def test_match_precedents_private_lending():
    matched = precedent_registry.match_precedents("民间借贷纠纷", "原告只有银行转账凭证没有借条，被告说是合伙投资款", top_k=2)
    assert len(matched) >= 1
    # 应当优先命中指导案例第72号
    assert any("72号" in m.case_name for m in matched)


def test_match_precedents_construction():
    matched = precedent_registry.match_precedents("建设工程施工合同纠纷", "实际施工人挂靠总包承建工程，要求发包人还钱", top_k=2)
    assert len(matched) >= 1
    assert any("103号" in m.case_name or "施工" in m.case_name for m in matched)


def test_match_precedents_traffic_accident():
    matched = precedent_registry.match_precedents("机动车交通事故责任纠纷", "交警认定主次责任，交强险先行赔付限额与医疗费", top_k=2)
    assert len(matched) >= 1
    assert any("24号" in m.case_name for m in matched)


def test_match_precedents_lease_contract():
    matched = precedent_registry.match_precedents("房屋租赁合同纠纷", "租客提前退租，房东扣留全部押金并要求巨额违约金", top_k=2)
    assert len(matched) >= 1
    assert any("提前退租" in m.case_name or "空置期" in m.case_name for m in matched)

