import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage
from app.multi_agent.contracts import (
    ExecutionTier,
    GraphClueArtifact,
    ReviewVerdictArtifact,
    SQLAuditArtifact,
)
from app.multi_agent.hub_orchestrator import MultiAgentHubOrchestrator
from app.orchestration.graph_route_coordinator import route_aligner_post


def test_route_aligner_post_dispatches_l2_to_multi_agent_hub():
    l2_state = {"metadata": {"execution_tier": ExecutionTier.L2_MULTI_AGENT.value}}
    assert route_aligner_post(l2_state) == "MULTI_AGENT_HUB"

    l1_state = {"metadata": {"execution_tier": ExecutionTier.L1_SOLO_SQL.value}}
    assert route_aligner_post(l1_state) == "PLANNER"

    l0_state = {"metadata": {"execution_tier": ExecutionTier.L0_FAST.value}}
    assert route_aligner_post(l0_state) == "PLANNER"

    bypass_state = {"metadata": {"synthesis_done": True}}
    assert route_aligner_post(bypass_state) == "REPORTER"


@pytest.mark.asyncio
async def test_hub_orchestrator_runs_graph_sql_policy_and_merges_clean_deliverables():
    mock_graph = AsyncMock()
    mock_graph.investigate.return_value = GraphClueArtifact(
        succeeded=True,
        temp_table="fqz_temp_sl_ring01",
        entity_count=6,
        cypher_used="MATCH (p:Patient) RETURN p.psn_no AS id",
        summary="发现 6 名团伙成员",
    )

    rows = [
        {"psn_no": "P1", "medfee_sumamt": 1800.0},
        {"psn_no": "P2", "medfee_sumamt": 1800.0},
    ]
    mock_sql = AsyncMock()
    mock_sql.run_parallel.return_value = [
        SQLAuditArtifact(
            subtask_id="g1",
            focus_title="团伙侧载核算",
            sql_query="SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql INNER JOIN fqz_temp_sl_ring01 ON psn_no = id",
            raw_data=json.dumps(rows, ensure_ascii=False),
            row_count=2,
            total_amount=3600.0,
            validated=True,
        )
    ]

    mock_policy = AsyncMock()
    mock_policy.review.return_value = ReviewVerdictArtifact(
        exemption_notes="核实无合规代办委托，属典型共享手机号团伙骗保。",
        statutory_citations=["《医疗保障基金使用监督管理条例》第十九条"],
        risk_level="高",
        adjusted_summary="定性高风险团伙骗保。",
    )

    hub = MultiAgentHubOrchestrator(
        graph_agent=mock_graph,
        sql_agent=mock_sql,
        policy_agent=mock_policy,
    )
    state = {
        "session_id": "sess-l2",
        "current_turn_query": "排查共用手机号团伙骗保并汇总涉案结算金额",
        "metadata": {"user_question": "排查共用手机号团伙骗保并汇总涉案结算金额"},
    }

    patch_res = await hub.execute_hub(state, config={})
    assert patch_res["sql_validated"] is True
    assert patch_res["evidence_row_count"] == 2
    assert "fqz_temp_sl_ring01" in patch_res["sql_query"]
    assert "第十九条" in patch_res["methodology"]
    assert len(patch_res["messages"]) == 1
    assert patch_res["temp_table"] == "fqz_temp_sl_ring01"
    assert any("GRAPH_DETECTIVE" in t for t in patch_res["execution_trace"])
    assert any("POLICY_REVIEWER" in t for t in patch_res["execution_trace"])


@pytest.mark.asyncio
async def test_hub_orchestrator_skips_graph_for_multi_dimension_sweep():
    mock_graph = AsyncMock()
    mock_sql = AsyncMock()
    mock_sql.run_parallel.return_value = [
        SQLAuditArtifact(
            subtask_id="gender_drug",
            focus_title="性别用药互斥排查",
            sql_query="SELECT count() FROM fqz_fymx_test",
            raw_data=json.dumps([{"cnt": 3, "amt": 500.0}], ensure_ascii=False),
            row_count=1,
            total_amount=500.0,
            validated=True,
        )
    ]
    mock_policy = AsyncMock()
    mock_policy.review.return_value = ReviewVerdictArtifact(
        exemption_notes="无临床豁免",
        statutory_citations=[],
        risk_level="中",
        adjusted_summary="建议核查。",
    )

    hub = MultiAgentHubOrchestrator(
        graph_agent=mock_graph,
        sql_agent=mock_sql,
        policy_agent=mock_policy,
    )
    state = {
        "session_id": "sess-sweep",
        "current_turn_query": "进行全面体检排查异常",
        "metadata": {"user_question": "进行全面体检排查异常"},
    }

    patch_res = await hub.execute_hub(state, config={})
    mock_graph.investigate.assert_not_called()
    assert patch_res["sql_validated"] is True
    assert patch_res["evidence_row_count"] == 1


@pytest.mark.asyncio
async def test_aligner_stamps_execution_tier_l2_and_l0_fast():
    from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node

    l2_state = {
        "messages": [HumanMessage(content="排查共用手机号团伙骗保")],
        "metadata": {"session_id": "s-l2"},
    }
    with patch(
        "app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference",
        return_value=("排查共用手机号团伙骗保", "QUERY", []),
    ):
        with patch(
            "app.core.context.funnel.semantic_funnel.execute_alignment_flow",
            new_callable=AsyncMock,
            return_value={"temp_table": None, "explanation": "ok"},
        ):
            res_l2 = await orchestrate_aligner_node(l2_state)
            assert res_l2["metadata"]["execution_tier"] == ExecutionTier.L2_MULTI_AGENT.value

    l0_state = {
        "messages": [HumanMessage(content="查询男性用妇科药")],
        "metadata": {"fast_route_id": "rule_male_gynecology"},
    }
    with patch(
        "app.core.context.coreference_rewriter.coreference_rewriter.resolve_coreference",
        return_value=("查询男性用妇科药", "QUERY", []),
    ):
        res_l0 = await orchestrate_aligner_node(l0_state)
        assert res_l0["metadata"]["execution_tier"] == ExecutionTier.L0_FAST.value


def test_agent_graph_and_stream_renderer_include_multi_agent_hub():
    from app.orchestration.agent_graph import workflow
    from app.api.stream_protocol_renderer import StreamProtocolRenderer

    assert "MULTI_AGENT_HUB" in workflow.nodes
    packets = StreamProtocolRenderer().render_node_status("MULTI_AGENT_HUB", "MULTI_AGENT_HUB")
    assert any("异构多专家协同中枢" in p for p in packets)
