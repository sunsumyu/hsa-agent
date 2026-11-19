import pytest
from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState

@pytest.mark.asyncio
async def test_full_legal_case_pipeline():
    graph = build_legal_graph()
    initial_state = {
        "thread_id": "case-test-101",
        "messages": [],
        "metadata": {
            "cause": "民间借贷纠纷",
            "user_question": "张三向李四出具借条借款20万元，并有招商银行转账流水，借款到期后李四催讨未果。李四起诉要求偿还本金并支付利息。"
        },
        "current_step": "START",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [],
        "evidence_items": [],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None
    }

    result = await graph.ainvoke(initial_state)
    assert len(result["case_facts"]) > 0
    assert len(result["evidence_items"]) > 0
    assert len(result["dispute_foci"]) > 0
    assert result["error_log"] is None
    assert "【法官心证评判】" in result["final_disposition"]
