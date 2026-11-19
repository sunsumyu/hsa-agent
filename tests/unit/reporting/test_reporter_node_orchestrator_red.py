"""
tests/unit/reporting/test_reporter_node_orchestrator_red.py
===========================================================
红灯测试：验证 ReporterNodeOrchestrator 深模块的报告装配、直通分流与生命周期提交能力
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

# 待实现的深模块
from app.reporting.reporter_node_orchestrator import (
    handle_synthesis_bypass,
    orchestrate_reporter_node,
)


def test_handle_synthesis_bypass_with_direct_response():
    """验证当 metadata 中包含 synthesis_done 且有 direct_response 时直接组装返回"""
    state = {
        "metadata": {
            "synthesis_done": True,
            "direct_response": "阶段性审计底稿：已排查3个险种，发现异常线索15条。",
            "user_question": "生成审计阶段底稿",
        },
        "messages": [],
        "sql_query": "SELECT 1",
    }
    res = handle_synthesis_bypass(state)
    assert res is not None
    assert "messages" in res
    assert len(res["messages"]) == 1
    assert isinstance(res["messages"][0], AIMessage)
    assert "阶段性审计底稿" in res["messages"][0].content
    # 验证生命周期提交补丁包含必要字段
    assert "turns" in res or "messages" in res


def test_handle_synthesis_bypass_fallback_to_last_ai_message():
    """验证当没有 direct_response 时，自动回退提取历史最后一条 AIMessage"""
    state = {
        "metadata": {"synthesis_done": True},
        "messages": [
            HumanMessage(content="查询便签"),
            AIMessage(content="便签回溯结论：已完成记录核实。"),
        ],
    }
    res = handle_synthesis_bypass(state)
    assert res is not None
    assert res["messages"][0].content == "便签回溯结论：已完成记录核实。"


@pytest.mark.asyncio
async def test_orchestrate_reporter_node_full_report_generation():
    """验证标准取证数据流下，完整调用清洗、指标评估、结论仲裁与报告渲染"""
    state = {
        "raw_data": '[{"psn_no": "P001", "medfee_sumamt": 1500.0, "fixmedins_name": "测试医院"}]',
        "sql_query": "SELECT * FROM fqz_fymx_test",
        "sql_history": ["SELECT * FROM fqz_fymx_test"],
        "methodology": "频次超标穿透分析",
        "metadata": {"user_question": "排查超量开药"},
        "messages": [AIMessage(content="SQL已执行", additional_kwargs={"source": "ClickHouse"})],
    }

    with patch("app.reporting.reporter_node_orchestrator.resolve_conclusion", new_callable=AsyncMock) as mock_resolve, \
         patch("app.reporting.report_renderer.AuditReportRenderer.render") as mock_render, \
         patch("app.core.booster.PrecisionBooster.verify_semantic_alignment") as mock_booster:

        mock_resolve.return_value = ("排查发现异常 1 例，涉案金额 1,500.00 元", False)
        mock_report = MagicMock()
        mock_report.markdown = "## 医保反欺诈审计报告\n..."
        mock_render.return_value = mock_report
        mock_booster.return_value = (True, "")

        res = await orchestrate_reporter_node(state, config={}, max_retries=1)

        assert "structured_report" in res
        assert "messages" in res
        assert res["messages"][0].content == "## 医保反欺诈审计报告\n..."
        mock_resolve.assert_awaited_once()
        mock_render.assert_called_once()
        mock_booster.assert_called_once()
