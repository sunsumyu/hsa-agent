from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agents.consolidator_agent import AuditConsolidatorAgent, ConsolidationPayload
from app.core.state_governance import create_turn_reset_patch
from app.multi_agent.contracts import GraphClueArtifact, ReviewVerdictArtifact, SQLAuditArtifact
from app.multi_agent.hub_orchestrator import MultiAgentHubOrchestrator
from app.skills.federated.federated_sideload_buffer import FederatedSideloadBuffer


def test_turn_reset_patch_clears_execution_tier_and_plan():
    stale_state = {
        "metadata": {
            "user_question": "上一轮问题",
            "execution_tier": "L2_MULTI_AGENT",
            "execution_plan": {"tier": "L2_MULTI_AGENT", "requires_graph": True},
            "fast_route_id": "GENDER_CONFLICT",
        }
    }
    patch = create_turn_reset_patch(stale_state)
    assert patch["metadata"]["execution_tier"] is None
    assert patch["metadata"]["execution_plan"] is None
    assert patch["metadata"]["user_question"] == "上一轮问题"


@pytest.mark.asyncio
async def test_consolidator_skips_single_sql_action_cache_for_l2_multi_sql(monkeypatch):
    mock_action_cache = MagicMock()
    mock_exp = MagicMock()
    monkeypatch.setattr("app.agents.consolidator_agent.action_cache_manager", mock_action_cache)
    monkeypatch.setattr("app.agents.consolidator_agent.experience_manager", mock_exp)

    mock_episodic = MagicMock()
    mock_episodic.record_episode = AsyncMock()
    mock_hub = MagicMock(episodic=mock_episodic)
    monkeypatch.setattr("app.core.memory.manager.memory_hub", mock_hub)

    payload = ConsolidationPayload(
        user_input="全面综合飞检",
        tasks=["性别", "退费"],
        sql="SELECT 2",
        sql_history=["SELECT 1", "SELECT 2"],
        methodology="L2",
        is_successful=True,
        execution_tier="L2_MULTI_AGENT",
    )
    await AuditConsolidatorAgent().persist_payload(payload)

    mock_action_cache.save.assert_not_called()
    mock_exp.save_audit_experience.assert_not_called()
    mock_episodic.record_episode.assert_awaited_once()


def test_sideload_buffer_drops_only_prefixed_temp_tables():
    from types import SimpleNamespace

    buf = FederatedSideloadBuffer()
    fake_client = SimpleNamespace(execute=MagicMock())
    assert buf.drop_temp_table("fqz_fymx_test", client=fake_client) is False
    fake_client.execute.assert_not_called()

    assert buf.drop_temp_table("fqz_temp_sl_1234abcd", client=fake_client) is True
    fake_client.execute.assert_called_once_with("DROP TABLE IF EXISTS fqz_temp_sl_1234abcd")


@pytest.mark.asyncio
async def test_hub_cleans_up_sideload_temp_table_even_if_sql_fails(monkeypatch):
    dropped = []
    monkeypatch.setattr(
        "app.skills.federated.federated_sideload_buffer.federated_sideload_buffer.drop_temp_table",
        lambda tbl: dropped.append(tbl) or True,
    )

    mock_graph = AsyncMock()
    mock_graph.investigate.return_value = GraphClueArtifact(
        succeeded=True, temp_table="fqz_temp_sl_deadbeef", entity_count=2
    )
    mock_sql = AsyncMock()
    mock_sql.run_parallel.side_effect = RuntimeError("sql failure")
    mock_policy = AsyncMock()
    mock_policy.review.return_value = ReviewVerdictArtifact()

    hub = MultiAgentHubOrchestrator(graph_agent=mock_graph, sql_agent=mock_sql, policy_agent=mock_policy)
    with pytest.raises(RuntimeError, match="sql failure"):
        await hub.execute_hub({"current_turn_query": "排查共用手机号团伙", "metadata": {}})

    assert dropped == ["fqz_temp_sl_deadbeef"]
