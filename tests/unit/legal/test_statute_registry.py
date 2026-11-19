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
