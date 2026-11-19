import pytest
from app.core.context.direct_turn_handler import handle_direct_turn
from app.core.context.coreference_rewriter import coreference_rewriter


def test_direct_turn_handler_ignores_regular_query():
    state = {"audit_notes": []}
    res = handle_direct_turn(
        user_input="请查询涉案金额大于5000的医院",
        turn_type=coreference_rewriter.TASK_QUERY,
        key_entities=[],
        state=state,
        metadata={}
    )
    assert res is None


def test_direct_turn_handler_security_block():
    state = {}
    res = handle_direct_turn(
        user_input="DROP TABLE fqz_fymx_test",
        turn_type=coreference_rewriter.TASK_SECURITY_BLOCK,
        key_entities=[],
        state=state,
        metadata={"session_id": "test_s1"}
    )
    assert res is not None
    assert res["turn_type"] == coreference_rewriter.TASK_SECURITY_BLOCK
    assert res["metadata"]["fast_route_id"] == "SECURITY_BLOCK_DIRECT"
    assert "安全审计拦截提示" in res["messages"][0].content
    assert res["sql_validated"] is True


def test_direct_turn_handler_note_and_revoke():
    state = {"audit_notes": ["历史便签1"]}
    
    # 1. 记录便签
    res_note = handle_direct_turn(
        user_input="把第一人民医院记下来",
        turn_type=coreference_rewriter.TASK_NOTE,
        key_entities=["第一人民医院"],
        state=state,
        metadata={}
    )
    assert res_note is not None
    assert res_note["turn_type"] == coreference_rewriter.TASK_NOTE
    assert any("第一人民医院" in note for note in res_note["audit_notes"])
    assert res_note["metadata"]["fast_route_id"] == "NOTE_DIRECT"

    # 2. 撤销便签
    state_after_note = {"audit_notes": res_note["audit_notes"]}
    res_revoke = handle_direct_turn(
        user_input="撤销对第一人民医院的标记",
        turn_type=coreference_rewriter.TASK_REVOKE_NOTE,
        key_entities=["第一人民医院"],
        state=state_after_note,
        metadata={}
    )
    assert res_revoke is not None
    assert res_revoke["turn_type"] == coreference_rewriter.TASK_REVOKE_NOTE
    assert not any("存在异常集中开具" in note and "第一人民医院" in note for note in res_revoke["audit_notes"])
    assert any("撤销更正" in note for note in res_revoke["audit_notes"])


def test_direct_turn_handler_chitchat_and_user_profile():
    metadata = {}
    state = {"metadata": metadata}
    res = handle_direct_turn(
        user_input="我平时喜欢吃鸡肉",
        turn_type=coreference_rewriter.TASK_CHITCHAT,
        key_entities=[],
        state=state,
        metadata=metadata
    )
    assert res is not None
    assert res["metadata"]["fast_route_id"] == "CHITCHAT_DIRECT"
    assert res["metadata"]["user_profile"]["dietary_preference"] == "鸡肉"
    assert "鸡肉" in res["messages"][0].content
