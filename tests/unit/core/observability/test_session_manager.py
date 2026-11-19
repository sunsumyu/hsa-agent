# tests/unit/core/observability/test_session_manager.py
# -*- coding: utf-8 -*-
import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.observability.session_manager import SessionContextManager


def test_build_turn_config():
    cfg = SessionContextManager.build_turn_config(
        session_id="audit-sess-99",
        turn_index=2,
        action_name="无手术麻醉核查"
    )
    assert cfg["run_name"] == "Audit-Turn-2: 无手术麻醉核查"
    assert "turn:2" in cfg["tags"]
    assert "multi-turn-audit" in cfg["tags"]
    assert cfg["metadata"]["session_id"] == "audit-sess-99"
    assert cfg["metadata"]["turn"] == 2
    assert cfg["configurable"]["thread_id"] == "audit-sess-99"


def test_build_turn_config_with_base_and_extra_meta():
    base_cfg = {
        "tags": ["prod"],
        "metadata": {"env": "production"},
        "configurable": {"model": "gpt-4"}
    }
    cfg = SessionContextManager.build_turn_config(
        session_id="audit-sess-100",
        turn_index=3,
        action_name="超限用药审查",
        extra_meta={"department": "心内科"},
        base_config=base_cfg
    )
    assert cfg["run_name"] == "Audit-Turn-3: 超限用药审查"
    assert set(cfg["tags"]) == {"prod", "turn:3", "multi-turn-audit"}
    assert cfg["metadata"]["session_id"] == "audit-sess-100"
    assert cfg["metadata"]["turn"] == 3
    assert cfg["metadata"]["env"] == "production"
    assert cfg["metadata"]["department"] == "心内科"
    assert cfg["configurable"]["thread_id"] == "audit-sess-100"
    assert cfg["configurable"]["model"] == "gpt-4"


def test_compact_history_below_threshold():
    history = [
        SystemMessage(content="系统人设"),
        HumanMessage(content="问1"), AIMessage(content="答1"),
        HumanMessage(content="问2"), AIMessage(content="答2")
    ]
    compacted = SessionContextManager.compact_history_if_needed(history, max_retained_turns=3)
    assert len(compacted) == 5
    assert compacted == history


def test_compact_history_exceeds_threshold():
    history = [
        SystemMessage(content="系统人设"),
        HumanMessage(content="问1"), AIMessage(content="答1"),
        HumanMessage(content="问2"), AIMessage(content="答2"),
        HumanMessage(content="问3"), AIMessage(content="答3"),
        HumanMessage(content="问4"), AIMessage(content="答4"),
        HumanMessage(content="问5"), AIMessage(content="答5")
    ]
    compacted = SessionContextManager.compact_history_if_needed(history, max_retained_turns=2)
    # 期望保留：系统人设 + 前置会话历史摘要 + 最近 2 轮问答(4条)
    assert len(compacted) == 1 + 1 + 4
    assert isinstance(compacted[0], SystemMessage)
    assert "【前置多轮审计问答摘要】" in compacted[1].content
    assert compacted[-1].content == "答5"


def test_compact_history_empty_and_no_system_message():
    assert SessionContextManager.compact_history_if_needed([]) == []

    # 无 SystemMessage 超过阈值
    history = [
        HumanMessage(content="问1"), AIMessage(content="答1"),
        HumanMessage(content="问2"), AIMessage(content="答2"),
        HumanMessage(content="问3"), AIMessage(content="答3")
    ]
    compacted = SessionContextManager.compact_history_if_needed(history, max_retained_turns=1)
    # 期望保留：前置摘要(SystemMessage) + 最近 1 轮问答(2条)
    assert len(compacted) == 1 + 2
    assert isinstance(compacted[0], SystemMessage)
    assert "【前置多轮审计问答摘要】" in compacted[0].content
    assert compacted[-2].content == "问3"
    assert compacted[-1].content == "答3"
