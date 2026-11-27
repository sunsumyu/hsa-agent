import pytest
import json
from langchain_core.messages import AIMessage
from app.core.context.coreference_rewriter import coreference_rewriter
from app.core.context.direct_turn_dispatcher import (
    DirectTurnDispatcher,
    DirectTurnContext,
    build_direct_turn_response,
)
from app.core.context.direct_turn_handler import handle_direct_turn


def test_build_direct_turn_response_structure():
    resp = build_direct_turn_response(
        user_input="你好",
        turn_type="CHITCHAT",
        fast_route_id="TEST_DIRECT",
        content="你好，很高兴为您服务！",
        raw_data_items=[{"status": "OK"}],
        sql_comment="无需查库",
        metadata={"session_id": "s123"},
        audit_notes=["便签1"],
    )

    assert resp["current_turn_query"] == "你好"
    assert resp["turn_type"] == "CHITCHAT"
    assert isinstance(resp["messages"][0], AIMessage)
    assert resp["messages"][0].content == "你好，很高兴为您服务！"
    assert json.loads(resp["raw_data"]) == [{"status": "OK"}]
    assert resp["sql_query"] == "--无需查库" or "无需查库" in resp["sql_query"]
    assert resp["sql_validated"] is True
    assert resp["error_log"] is None
    assert resp["audit_notes"] == ["便签1"]
    assert resp["metadata"]["synthesis_done"] is True
    assert resp["metadata"]["fast_route_id"] == "TEST_DIRECT"
    assert resp["metadata"]["direct_response"] == "你好，很高兴为您服务！"


def test_dispatcher_handles_all_direct_types():
    dispatcher = DirectTurnDispatcher()

    # 1. Synthesis
    ctx_synth = DirectTurnContext(
        user_input="总结当前审计工作底稿",
        turn_type=coreference_rewriter.TASK_SYNTHESIS,
        key_entities=[],
        state={"messages": [], "metadata": {}},
        metadata={},
    )
    res_synth = dispatcher.dispatch(ctx_synth)
    assert res_synth is not None
    assert res_synth["metadata"]["fast_route_id"] == "SYNTHESIS_DIRECT"

    # 2. Recall
    ctx_recall = DirectTurnContext(
        user_input="回顾刚才标记的医院",
        turn_type=coreference_rewriter.TASK_RECALL,
        key_entities=[],
        state={"audit_notes": ["涉案机构: 第一医院"]},
        metadata={},
    )
    res_recall = dispatcher.dispatch(ctx_recall)
    assert res_recall is not None
    assert res_recall["metadata"]["fast_route_id"] == "RECALL_DIRECT"

    # 3. Consolidate
    ctx_cons = DirectTurnContext(
        user_input="将本次核查逻辑沉淀为经验",
        turn_type=coreference_rewriter.TASK_CONSOLIDATE,
        key_entities=[],
        state={},
        metadata={},
    )
    res_cons = dispatcher.dispatch(ctx_cons)
    assert res_cons is not None
    assert res_cons["metadata"]["fast_route_id"] == "CONSOLIDATE_DIRECT"
    assert "经验库" in res_cons["messages"][0].content


def test_chitchat_subroutes():
    dispatcher = DirectTurnDispatcher()

    # 问候
    ctx_greeting = DirectTurnContext(
        user_input="你好呀",
        turn_type=coreference_rewriter.TASK_CHITCHAT,
        key_entities=[],
        state={},
        metadata={},
    )
    res_greeting = dispatcher.dispatch(ctx_greeting)
    assert "智能医保稽核助手" in res_greeting["messages"][0].content

    # 自我介绍
    ctx_intro = DirectTurnContext(
        user_input="介绍一下你的功能",
        turn_type=coreference_rewriter.TASK_CHITCHAT,
        key_entities=[],
        state={},
        metadata={},
    )
    res_intro = dispatcher.dispatch(ctx_intro)
    assert "核心专长" in res_intro["messages"][0].content

    # 默认闲聊
    ctx_default = DirectTurnContext(
        user_input="今天天气真不错",
        turn_type=coreference_rewriter.TASK_CHITCHAT,
        key_entities=[],
        state={},
        metadata={},
    )
    res_default = dispatcher.dispatch(ctx_default)
    assert "专职于医保大数据核查" in res_default["messages"][0].content


def test_handle_direct_turn_backward_compatibility():
    # 常规 QUERY 返回 None
    assert handle_direct_turn(
        user_input="查询医院",
        turn_type=coreference_rewriter.TASK_QUERY,
        key_entities=[],
        state={},
    ) is None
