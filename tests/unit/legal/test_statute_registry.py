import pytest
from domains.legal.registry.statute_registry import StatuteRegistry

def test_statute_registry_load_private_lending():
    registry = StatuteRegistry()
    schema = registry.get_cause_of_action("民间借贷纠纷")
    assert schema is not None
    assert schema.cause_of_action == "民间借贷纠纷"
    
    element_ids = [el.element_id for el in schema.essential_elements]
    assert "consensus" in element_ids
    assert "actual_delivery" in element_ids
    assert "interest_rate" in element_ids

    delivery_el = schema.get_element("actual_delivery")
    assert delivery_el.is_mandatory_for_natural_person is True
    assert "银行转账凭证" in delivery_el.accepted_evidence_types


def test_statute_registry_load_traffic_accident():
    registry = StatuteRegistry()
    schema = registry.get_cause_of_action("机动车交通事故责任纠纷")
    assert schema is not None
    element_ids = [el.element_id for el in schema.essential_elements]
    assert "accident_fact_and_liability" in element_ids
    assert "compulsory_and_commercial_insurance" in element_ids
    assert "medical_and_treatment_expenses" in element_ids


def test_statute_registry_load_lease_contract():
    registry = StatuteRegistry()
    schema = registry.get_cause_of_action("房屋租赁合同纠纷")
    assert schema is not None
    element_ids = [el.element_id for el in schema.essential_elements]
    assert "lease_contract_and_delivery" in element_ids
    assert "rent_and_deposit_payments" in element_ids
    assert "break_lease_penalty_and_vacancy_loss" in element_ids

