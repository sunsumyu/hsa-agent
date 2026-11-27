"""
tests/unit/agents/test_fast_route_executor_red.py
=================================================
红灯测试：验证 FastRouteExecutor 深模块的快速路由物理直通与零行回退分流能力
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage

# 待实现的深模块
from app.agents.fast_route_executor import (
    execute_fast_route_bypass,
    FastRouteExecutionResult,
)
from app.core.structured_tracer import StructuredTracer


@pytest.mark.asyncio
async def test_fast_route_not_triggered_when_no_route_id():
    """验证当 metadata 中没有 fast_route_id 时，直接返回 handled=False"""
    state = {"metadata": {}}
    tracer = StructuredTracer(session_id="test_sess")

    res = await execute_fast_route_bypass(
        state=state,
        tools=[],
        tracer=tracer,
        retry=0
    )
    assert isinstance(res, FastRouteExecutionResult)
    assert res.handled is False
    assert res.fallback_to_llm is False
    assert res.state_update is None


@pytest.mark.asyncio
async def test_fast_route_success_bypass():
    """验证快速路由命中且物理执行产出有效数据时，直接完成取证并组装最终状态输出"""
    state = {
        "metadata": {"fast_route_id": "rule_male_gynecology", "extra_filters": "admdvs = '4401'"},
        "temp_table": None,
    }
    tracer = StructuredTracer(session_id="test_sess")

    mock_results = [{"raw_data": '[{"psn_no": "P001", "fee": 100}]'}]

    with patch("app.agents.fast_route_executor.invoke_tools_safely", new_callable=AsyncMock) as mock_invoke, \
         patch("app.agents.fast_route_executor.tool_evidence_extractor") as mock_extractor:
        
        mock_invoke.return_value = mock_results
        mock_evidence = MagicMock()
        mock_evidence.to_dict.return_value = {
            "raw_data": '[{"psn_no": "P001", "fee": 100}]',
            "sql_query": "SELECT * FROM fqz_fymx_test WHERE gend = '1'",
            "sql_history": ["SELECT * FROM fqz_fymx_test WHERE gend = '1'"],
            "methodology": "静态规则直通",
            "tool_msgs": [],
            "has_error": False,
            "error_msg": None,
        }
        mock_extractor.process.return_value = mock_evidence

        res = await execute_fast_route_bypass(
            state=state,
            tools=[MagicMock(name="audit_medical_rule")],
            tracer=tracer,
            retry=0
        )

        assert res.handled is True
        assert res.fallback_to_llm is False
        assert res.state_update is not None
        assert res.state_update["sql_validated"] is True
        assert res.state_update["raw_data"] == '[{"psn_no": "P001", "fee": 100}]'
        assert len(res.state_update["messages"]) == 1
        assert isinstance(res.state_update["messages"][0], AIMessage)


@pytest.mark.asyncio
async def test_fast_route_fallback_to_llm_when_empty_result():
    """验证当快速路由物理执行返回 0 行时，自动触发 Fallback 机制：清除 route_id 并注入 sql_history"""
    state = {
        "metadata": {"fast_route_id": "rule_empty_sample"},
        "sql_history": ["SELECT 1"],
    }
    tracer = StructuredTracer(session_id="test_sess")

    with patch("app.agents.fast_route_executor.invoke_tools_safely", new_callable=AsyncMock) as mock_invoke, \
         patch("app.agents.fast_route_executor.tool_evidence_extractor") as mock_extractor:
        
        mock_invoke.return_value = []
        mock_evidence = MagicMock()
        mock_evidence.to_dict.return_value = {
            "raw_data": "[]",
            "sql_query": "SELECT * FROM fqz_empty",
            "sql_history": ["SELECT 1", "SELECT * FROM fqz_empty"],
            "methodology": "静态规则直通",
            "tool_msgs": [],
            "has_error": False,
            "error_msg": None,
        }
        mock_extractor.process.return_value = mock_evidence

        res = await execute_fast_route_bypass(
            state=state,
            tools=[],
            tracer=tracer,
            retry=0
        )

        assert res.handled is True
        assert res.fallback_to_llm is True
        # 验证 fast_route_id 已从 metadata 中安全剔除，避免死循环
        assert "fast_route_id" not in state["metadata"]
        # 验证尝试过的 sql 已安全落入 sql_history
        assert "SELECT * FROM fqz_empty" in state["sql_history"]
        assert res.state_update is None
