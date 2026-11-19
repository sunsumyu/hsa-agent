"""
tests/unit/core/test_context_budget_and_renderer_red.py
======================================================
[Matt Pocock Deep Module Red Test] 上下文预算调度与事实载荷渲染解耦架构审计
"""

import datetime
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.context.context_builder import ContextPacket, ContextConfig
from app.core.context.context_budget_scheduler import ContextBudgetScheduler
from app.core.context.context_payload_renderer import ContextPayloadRenderer


def test_context_budget_scheduler_priority_and_greedy_fit():
    """验证预算调度器高优先级强保留与贪心预算装配"""
    scheduler = ContextBudgetScheduler(config=ContextConfig(max_tokens=500, min_relevance=0.1))

    high_p1 = ContextPacket(
        content="High priority note",
        relevance_score=1.0,
        metadata={"priority": "high", "type": "note_evidence"}
    )
    low_p1 = ContextPacket(
        content="Relevant search content query match",
        relevance_score=0.8,
        metadata={"type": "cognitive_memory"}
    )
    low_p2 = ContextPacket(
        content="Irrelevant unrelated fluff",
        relevance_score=0.01,
        metadata={"type": "cognitive_memory"}
    )

    selected = scheduler.schedule(
        packets=[high_p1, low_p1, low_p2],
        query="query search match",
        budget=400,
        schema_selector=MagicMock(),
    )

    assert high_p1 in selected
    assert low_p1 in selected
    assert low_p2 not in selected  # 因相关性低于阈值被过滤


def test_context_payload_renderer_prefix_cache_ordering_and_dedup():
    """验证事实载荷渲染器的前缀缓存顺序（DDL 最先）与防多轮重复注入"""
    renderer = ContextPayloadRenderer()

    packets = [
        ContextPacket(
            content="<table name='fqz_fymx_test'/>",
            metadata={"type": "clickhouse_schema"}
        ),
        ContextPacket(
            content="<note>patient is checked</note>",
            metadata={"type": "note_evidence"}
        ),
        ContextPacket(
            content="<semantic_alignment>icd10=E11</semantic_alignment>",
            metadata={"type": "semantic_alignment"}
        )
    ]

    history = [
        SystemMessage(content="You are an audit agent."),
        SystemMessage(content="【当前审计黄金上下文载荷 (GSSC 动态精选渲染版)】：old dirty payload"),
        HumanMessage(content="Start investigation.")
    ]

    messages = renderer.render(packets, history)

    # 1. 验证旧载荷已被剔除
    old_payload_count = sum(1 for m in messages if "old dirty payload" in str(m.content))
    assert old_payload_count == 0

    # 2. 验证新载荷生成且包含 ephemeral cache_control
    gssc_msg = next((m for m in messages if "【当前审计黄金上下文载荷" in str(m.content)), None)
    assert gssc_msg is not None
    assert gssc_msg.additional_kwargs.get("cache_control") == {"type": "ephemeral"}

    # 3. 验证静态 Schema 严格排在动态对齐和 Notes 之前
    content = str(gssc_msg.content)
    idx_schema = content.find("<database_schema_context>")
    idx_align = content.find("icd10=E11")
    idx_note = content.find("<structured_audit_notes>")

    assert idx_schema != -1
    assert idx_align != -1
    assert idx_note != -1
    assert idx_schema < idx_align < idx_note


def test_context_budget_scheduler_preserves_explicit_score_and_falls_back_on_none():
    """验证未打分包(None)走 Jaccard 兜底，已打分包(含 0.5)不被覆盖"""
    scheduler = ContextBudgetScheduler(config=ContextConfig(max_tokens=500, min_relevance=0.2))

    # 1. 未传 relevance_score -> 默认 None -> 由 Jaccard 计算
    unscored_match = ContextPacket(
        content="query search match",
        metadata={"type": "cognitive_memory"},
    )
    assert unscored_match.relevance_score is None

    # 2. 显式传入 0.5（即使与英文分词 Jaccard 为 0，也不应被误判为未计算而覆盖）
    explicit_half = ContextPacket(
        content="中文语义检索命中的历史审计经验",
        relevance_score=0.5,
        metadata={"type": "cognitive_memory"},
    )

    # 3. 显式传入 0.05（低于 min_relevance，应被过滤）
    explicit_low = ContextPacket(
        content="query search match",
        relevance_score=0.05,
        metadata={"type": "cognitive_memory"},
    )

    selected = scheduler.schedule(
        packets=[unscored_match, explicit_half, explicit_low],
        query="query search match",
        budget=400,
        schema_selector=MagicMock(),
    )

    assert unscored_match in selected
    assert unscored_match.relevance_score == pytest.approx(1.0)
    assert explicit_half in selected
    assert explicit_half.relevance_score == pytest.approx(0.5)
    assert explicit_low not in selected

