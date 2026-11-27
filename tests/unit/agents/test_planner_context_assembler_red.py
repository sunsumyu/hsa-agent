"""
tests/unit/agents/test_planner_context_assembler_red.py
======================================================
红灯测试：验证 PlannerContextAssembler 深模块的意图扩展、轻重提示词装配与紧凑输出裁剪能力
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

# 待提取的目标深模块
from app.agents.planner_context_assembler import (
    enrich_user_intent,
    assemble_planner_hints,
    build_planner_prompt,
    format_compact_plan_message,
    assemble_planner_context,
    PlannerContextPayload,
)


def test_enrich_user_intent_with_expansion():
    """验证当 Neo4j 存在医学关键词扩展时，原查询被丰富且保留核心语意"""
    with patch("app.agents.planner_context_assembler.expand_medical_intent") as mock_expand:
        mock_expand.return_value = ["限定用药", "超剂量"]
        enriched = enrich_user_intent("核查抗生素处方")
        assert "限定用药" in enriched
        assert "核查范围应包含但不限于" in enriched


def test_enrich_user_intent_no_expansion():
    """验证无扩展词时直接原样返回"""
    with patch("app.agents.planner_context_assembler.expand_medical_intent") as mock_expand:
        mock_expand.return_value = []
        enriched = enrich_user_intent("简单统计")
        assert enriched == "简单统计"


@pytest.mark.asyncio
async def test_assemble_planner_hints_heavy():
    """验证 heavy 模式下直接启用 GSSC 统一引擎引导语，不消耗 memory_hub IO"""
    schema_hint, exp_hint = await assemble_planner_hints("planner_heavy", "查询某机构")
    assert "GSSC 统一引擎" in schema_hint
    assert "GSSC 统一引擎" in exp_hint


@pytest.mark.asyncio
async def test_assemble_planner_hints_light():
    """验证 light 模式下查询 memory_hub 并组装语义与经验提示"""
    with patch("app.agents.planner_context_assembler.memory_hub") as mock_hub:
        mock_hub.query = AsyncMock(return_value=["item1"])
        mock_hub.semantic.format_for_prompt.return_value = "Schema提示内容"
        mock_hub.semantic.get_avoidance_guides.return_value = "避坑指南"
        mock_hub.episodic.recall_experience = AsyncMock(return_value=[])
        mock_hub.episodic.format_experience_for_prompt.return_value = "历史经验"

        schema_hint, exp_hint = await assemble_planner_hints("planner_light", "查询某机构")
        assert "Schema提示内容" in schema_hint
        assert "避坑指南" in schema_hint
        assert exp_hint == "历史经验"


def test_format_compact_plan_message_limits_length_and_tasks():
    """验证产出的 compact message 截取方法论前300字符与前3条任务，阻断上下文膨胀"""
    long_methodology = "通过多维度穿透比对分析。" * 40
    many_tasks = [f"任务{i}: 执行步骤" for i in range(10)]

    msg = format_compact_plan_message(long_methodology, many_tasks)
    assert isinstance(msg, AIMessage)
    assert "【审计规划指引】" in msg.content
    assert len(msg.content) < 600
    assert "- 任务0: 执行步骤" in msg.content
    assert "- 任务2: 执行步骤" in msg.content
    assert "- 任务5: 执行步骤" not in msg.content


@pytest.mark.asyncio
async def test_assemble_planner_context_full_flow():
    """验证 assemble_planner_context 一体化输出合法 PlannerContextPayload"""
    state = {
        "messages": [HumanMessage(content="排查重复住院收费")],
        "metadata": {"model_id": "HEAVY"}
    }
    with patch("app.agents.planner_context_assembler.neo4j_manager") as mock_neo4j:
        mock_neo4j.get_ontology.return_value = "(:Hospital)-[:SETTLE]->(:Patient)"

        payload = await assemble_planner_context(state, user_input="排查重复住院收费")
        assert isinstance(payload, PlannerContextPayload)
        assert payload.role == "planner_heavy"
        assert len(payload.prompt_messages) > 0
        assert payload.user_input_enriched != ""
