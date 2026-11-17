import pytest
from domains.legal.registry.statute_registry import StatuteRegistry

def test_statute_registry_load_sales_contract():
    registry = StatuteRegistry()
    schema = registry.get_cause_of_action("买卖合同纠纷")
    assert schema is not None
    assert schema.cause_of_action == "买卖合同纠纷"
    
    element_ids = [el.element_id for el in schema.essential_elements]
    assert "contract_formation" in element_ids
    assert "goods_delivery" in element_ids
    assert "inspection_and_acceptance" in element_ids
    assert "payment_obligation" in element_ids

    inspection_el = schema.get_element("inspection_and_acceptance")
    assert inspection_el.burden_of_proof == "defendant"  # 被告对质量异议承担举证责任
