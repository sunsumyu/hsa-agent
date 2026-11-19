"""
tests/unit/agents/test_coder_prompt_assembler_red.py
===================================================
红灯测试：验证 CoderPromptAssembler 深模块的上下文组装、消息紧凑裁剪与 Prompt 渲染能力
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# 待提取的目标深模块
from app.agents.coder_prompt_assembler import (
    compact_coder_messages,
    build_schema_hint,
    build_scenario_guidelines,
    resolve_ontology_context,
    assemble_coder_prompt,
    CoderPromptPayload,
)


def test_compact_coder_messages_truncates_long_ai_text():
    """验证长篇排版公文 (>300 chars) 被紧凑截断并附加归档标记，而 tool_calls 不受影响"""
    long_ai_text = "这是一篇关于医保欺诈排查的长篇审计分析公文报告。" * 20
    assert len(long_ai_text) > 300

    messages = [
        HumanMessage(content="查询超量开药明细"),
        AIMessage(content=long_ai_text),
        AIMessage(content="短消息正常保留"),
        AIMessage(content="带工具调用的消息" * 30, tool_calls=[{"name": "execute_audit_sql", "args": {}, "id": "call_123"}]),
    ]

    compacted = compact_coder_messages(messages, fallback_query="查询超量开药明细")
    assert len(compacted) == 4
    # 第2条长消息被截断
    assert "[前序审计结论已归档]" in compacted[1].content
    assert len(compacted[1].content) < 200
    # 第3条短消息保留
    assert compacted[2].content == "短消息正常保留"
    # 第4条带 tool_calls 的保留原样
    assert getattr(compacted[3], "tool_calls", None) is not None


def test_compact_coder_messages_fallback_when_empty():
    """验证当 state 中 messages 为空时，回退到当前轮次自包含问题"""
    compacted = compact_coder_messages([], fallback_query="查询违规基金总额")
    assert len(compacted) == 1
    assert isinstance(compacted[0], HumanMessage)
    assert compacted[0].content == "查询违规基金总额"


def test_build_schema_hint_contains_primary_and_warning():
    """验证 Schema Hint 包含场景主表建议与 ClickHouse 禁查元数据表安全警示"""
    hint, primary_tbl, _ = build_schema_hint("查询诊所过度诊疗费用明细")
    assert "【目标场景推荐物理主表】" in hint
    assert "ClickHouse" in hint
    assert "严禁查询 sqlite_master" in hint
    assert primary_tbl != ""


def test_resolve_ontology_context_selective_loading():
    """验证普通单表/双表查询裁剪图谱本体，仅在图谱团伙/手机号关联联邦场景加载"""
    normal_ontology = resolve_ontology_context("查询住院基金支出异常", methodology="按机构汇总分析")
    assert "暂无需加载图谱本体" in normal_ontology

    with patch("app.agents.coder_prompt_assembler.neo4j_manager") as mock_neo4j:
        mock_neo4j.get_ontology.return_value = "(:Person)-[:SHARED_PHONE]->(:Person)"
        graph_ontology = resolve_ontology_context("排查家庭医生签约团伙欺诈环", methodology="")
        assert "SHARED_PHONE" in graph_ontology


def test_build_scenario_guidelines_combines_intent_and_enforcement():
    """验证场景指引能够融合 AuditIntentPlanner 的提取指引与 SceneTableSelector 的强制提示"""
    guidelines = build_scenario_guidelines(
        user_q="分析同日重复收费异常",
        scene_enforcement="【场景强制提示】: 优先使用 fqz_fymx 表"
    )
    assert "【场景强制提示】" in guidelines


def test_assemble_coder_prompt_full_payload():
    """验证 assemble_coder_prompt 完整生命周期产出结构化 Payload 与合法的 messages 列表"""
    state = {
        "user_query": "查询近3个月诊所超频次结算",
        "tasks": ["任务1: 筛选超频次结算记录", "任务2: 计算涉案金额"],
        "methodology": "多维频次聚合过滤",
        "messages": [HumanMessage(content="查询近3个月诊所超频次结算")],
    }
    metadata = {"scene_enforcement": "【强制提示】: 关注频次窗口"}

    payload = assemble_coder_prompt(state, metadata=metadata)
    assert isinstance(payload, CoderPromptPayload)
    assert payload.user_query == "查询近3个月诊所超频次结算"
    assert len(payload.prompt_messages) > 0
    assert payload.primary_table != ""
    # 验证返回的 Prompt 消息包含 System/Human 等 BaseMessage
    assert any(getattr(m, "content", None) for m in payload.prompt_messages)
