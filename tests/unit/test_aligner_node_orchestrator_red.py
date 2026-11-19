import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_aligner_no_user_input():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node
    state = {"messages": []}
    res = await orchestrate_aligner_node(state)
    assert res == {}

@pytest.mark.asyncio
async def test_aligner_direct_turn_bypass():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node
    state = {
        "messages": [HumanMessage(content="你好，请问你是谁？")]
    }
    with patch("app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference", return_value=("你好，请问你是谁？", "GREETING", [])):
        with patch("app.core.context.aligner_node_orchestrator.handle_direct_turn", return_value={"messages": [HumanMessage(content="你好")], "turn_type": "GREETING", "current_turn_query": "你好，请问你是谁？"}):
            res = await orchestrate_aligner_node(state)
            assert res is not None
            assert "messages" in res
            assert "current_turn_query" in res
            assert res.get("turn_type") == "GREETING"

@pytest.mark.asyncio
async def test_aligner_fast_route_bypass():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node
    state = {
        "messages": [HumanMessage(content="查询男性用妇科药")],
        "metadata": {"fast_route_id": "rule_male_gynecology"}
    }
    with patch("app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference", return_value=("查询男性用妇科药", "QUERY", [])):
        with patch("app.core.context.funnel.semantic_funnel.execute_alignment_flow", new_callable=AsyncMock) as mock_funnel:
            res = await orchestrate_aligner_node(state)
            mock_funnel.assert_not_called()
            assert res.get("current_turn_query") == "查询男性用妇科药"
            assert res.get("turn_type") == "QUERY"
            assert res.get("metadata", {}).get("fast_route_id") == "rule_male_gynecology"

@pytest.mark.asyncio
async def test_aligner_full_semantic_funnel_success():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node
    state = {
        "messages": [HumanMessage(content="排查重复住院违规数据")],
        "metadata": {"session_id": "s123"},
        "raw_data": "old_dirty_data",
        "sql_query": "SELECT * FROM old",
        "sql_validated": True,
        "retry_count": 2,
        "error_log": "previous error"
    }
    fake_alignment = {
        "temp_table": "tmp_audit_123",
        "explanation": "匹配到住院结算主表"
    }
    with patch("app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference", return_value=("排查重复住院违规数据", "QUERY", ["重复住院"])):
        with patch("app.core.context.funnel.semantic_funnel.execute_alignment_flow", new_callable=AsyncMock, return_value=fake_alignment):
            res = await orchestrate_aligner_node(state)
            assert res.get("current_turn_query") == "排查重复住院违规数据"
            assert res.get("temp_table") == "tmp_audit_123"
            assert res.get("schema_hint") == "匹配到住院结算主表"
            # 验证单轮中间状态清洗
            assert res.get("raw_data") == ""
            assert res.get("sql_query") == ""
            assert res.get("sql_validated") is False
            assert res.get("error_log") is None
            assert res.get("retry_count") == 0

@pytest.mark.asyncio
async def test_aligner_funnel_exception_handling():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node
    state = {
        "messages": [HumanMessage(content="排查异常")],
        "metadata": {}
    }
    with patch("app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference", return_value=("排查异常", "QUERY", [])):
        with patch("app.core.context.funnel.semantic_funnel.execute_alignment_flow", new_callable=AsyncMock, side_effect=RuntimeError("Semantic Funnel Crash")):
            res = await orchestrate_aligner_node(state)
            assert res == {}
