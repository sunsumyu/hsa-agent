import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.coder_agent import AuditCoderAgent
from app.core.rag.citation_ledger import CitationRecord
from app.core.tool_engine.tool_evidence_extractor import ToolEvidenceExtractor
from app.multi_agent.contracts import (
    ExecutionTier,
    OrchestrationPlan,
    ReviewVerdictArtifact,
    SQLAuditArtifact,
    SubTaskSpec,
)
from app.multi_agent.hub_orchestrator import MultiAgentHubOrchestrator
from app.multi_agent.policy_reviewer_agent import PolicyReviewerSubagent
from app.multi_agent.sql_auditor_agent import SQLAuditorSubagent


def test_tool_evidence_extractor_harvests_law_rag_citations():
    law_output = (
        "【法规库检索报告 - 「骗保」 Top 1 条命中】\n"
        "1. [CITE:law_abcdef12] [来源: 行政法规/医疗保障基金使用监督管理条例.pdf | 第6页 | 哈希: 001122334455]\n"
        "   条文: 第十五条 定点医药机构不得分解住院。\n"
    )
    extractor = ToolEvidenceExtractor()
    processed = extractor.process(
        results=[({"id": "tc1", "name": "query_law_database"}, law_output)],
        state={"sql_history": [], "raw_data": "", "retrieved_citations": []},
    )
    assert len(processed.retrieved_citations) == 1
    assert processed.retrieved_citations[0]["citation_id"] == "law_abcdef12"
    assert processed.to_dict()["retrieved_citations"][0]["citation_id"] == "law_abcdef12"


def test_tool_evidence_extractor_preserves_existing_citations_across_sql_step():
    existing = [
        CitationRecord(
            citation_id="rag_11112222",
            source_type="vector_rag",
            source_doc="corpus.md",
            snippet="已有引文",
        ).model_dump(mode="json")
    ]
    extractor = ToolEvidenceExtractor()
    sql_res = {
        "status": "SUCCESS",
        "sql_logic": "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 100",
        "data": [{"psn_no": "P1", "medfee_sumamt": 200}],
    }
    processed = extractor.process(
        results=[({"id": "tc_sql", "name": "execute_audit_sql"}, sql_res)],
        state={"sql_history": [], "raw_data": "", "retrieved_citations": existing},
    )
    assert [c["citation_id"] for c in processed.retrieved_citations] == ["rag_11112222"]


@pytest.mark.asyncio
async def test_policy_reviewer_populates_citations_ledger_from_tools(monkeypatch):
    class FakeLawTool:
        name = "query_law_database"

        async def ainvoke(self, args):
            return (
                "【法规库检索报告 - 「重复收费」 Top 1 条命中】\n"
                "1. [CITE:law_99887766] [来源: 行政法规/医疗保障基金使用监督管理条例.pdf | 第5页 | 哈希: aabbcc112233]\n"
                "   条文: 第十五条 严禁重复收费。\n"
            )

    monkeypatch.setattr("app.multi_agent.policy_reviewer_agent._REVIEW_TOOLS", [FakeLawTool()])
    calls = 0

    async def fake_llm(role, messages, tools=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "tc1", "name": "query_law_database", "args": {"query": "重复收费"}}],
            )
        return AIMessage(content="经核查触发 [CITE:law_99887766]，风险等级：高")

    art = SQLAuditArtifact(subtask_id="s1", focus_title="重复收费", row_count=5, total_amount=2000.0, validated=True)
    verdict = await PolicyReviewerSubagent(llm_caller=fake_llm).review("重复收费核查", [art])
    ids = [c["citation_id"] for c in verdict.citations_ledger]
    assert "law_99887766" in ids


@pytest.mark.asyncio
async def test_hub_orchestrator_forwards_citations_ledger_and_omits_when_empty():
    ledger_item = CitationRecord(
        citation_id="law_99887766",
        source_type="law_rag",
        source_doc="行政法规/医疗保障基金使用监督管理条例.pdf",
        snippet="第十五条 严禁重复收费。",
    ).model_dump(mode="json")

    mock_graph = AsyncMock()
    mock_sql = AsyncMock()
    mock_sql.run_parallel.return_value = [
        SQLAuditArtifact(
            subtask_id="s1",
            focus_title="重复收费",
            sql_query="SELECT psn_no FROM fqz_fymx_test",
            raw_data=json.dumps([{"psn_no": "P1"}], ensure_ascii=False),
            row_count=1,
            total_amount=100.0,
            validated=True,
        )
    ]
    plan = OrchestrationPlan(
        tier=ExecutionTier.L2_MULTI_AGENT,
        requires_graph=False,
        requires_policy_review=True,
        subtasks=[SubTaskSpec(subtask_id="s1", focus_title="重复收费", query_instruction="查重复收费")],
        reason="test",
    )

    mock_policy_with_ledger = AsyncMock()
    mock_policy_with_ledger.review.return_value = ReviewVerdictArtifact(
        exemption_notes="高风险",
        statutory_citations=[],
        citations_ledger=[ledger_item],
        risk_level="高",
        adjusted_summary="高风险",
    )
    hub_with_ledger = MultiAgentHubOrchestrator(
        graph_agent=mock_graph,
        sql_agent=mock_sql,
        policy_agent=mock_policy_with_ledger,
    )
    state = {
        "session_id": "sess-1",
        "current_turn_query": "查重复收费",
        "metadata": {"execution_plan": plan.model_dump()},
    }
    patch_with_ledger = await hub_with_ledger.execute_hub(state, config={})
    assert patch_with_ledger["retrieved_citations"] == [ledger_item]

    mock_policy_empty = AsyncMock()
    mock_policy_empty.review.return_value = ReviewVerdictArtifact(
        exemption_notes="无",
        statutory_citations=[],
        citations_ledger=[],
        risk_level="中",
        adjusted_summary="无",
    )
    hub_empty = MultiAgentHubOrchestrator(
        graph_agent=mock_graph,
        sql_agent=mock_sql,
        policy_agent=mock_policy_empty,
    )
    patch_empty = await hub_empty.execute_hub(state, config={})
    assert "retrieved_citations" not in patch_empty


@pytest.mark.asyncio
async def test_coder_agent_omits_retrieved_citations_when_empty_and_forwards_when_non_empty():
    agent = AuditCoderAgent(max_retries=3)
    fake_tool = SimpleNamespace(name="execute_audit_sql")
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc1", "name": "execute_audit_sql", "args": {"sql": "SELECT 1"}}],
    )
    base_state = {
        "session_id": "sess-coder",
        "messages": [HumanMessage(content="核查重复收费")],
        "sql_history": [],
        "raw_data": "",
        "metadata": {"user_id": "u1"},
    }

    with (
        patch("app.agents.coder_agent.skill_registry.get_all_skills", return_value=[fake_tool]),
        patch("app.agents.coder_agent.permission_manager.filter_skills", return_value=[fake_tool]),
        patch(
            "app.agents.coder_agent.execute_fast_route_bypass",
            new=AsyncMock(return_value=SimpleNamespace(handled=False, fallback_to_llm=False)),
        ),
        patch(
            "app.agents.coder_agent.assemble_coder_prompt",
            return_value=SimpleNamespace(prompt_messages=[HumanMessage(content="p")], audit_intent="repeat"),
        ),
        patch(
            "app.agents.coder_agent.coordinate_coder_inference",
            new=AsyncMock(return_value=SimpleNamespace(has_tool_calls=True, response=ai_msg)),
        ),
        patch(
            "app.agents.coder_agent.check_pre_execution_gate",
            return_value=SimpleNamespace(passed=True),
        ),
        patch(
            "app.agents.coder_agent.check_post_execution_gate",
            return_value=SimpleNamespace(passed=True),
        ),
    ):
        sql_only_res = [
            (
                {"id": "tc1", "name": "execute_audit_sql"},
                {
                    "status": "SUCCESS",
                    "sql_logic": "SELECT psn_no FROM fqz_fymx_test",
                    "data": [{"psn_no": "P1"}],
                },
            )
        ]
        with patch.object(agent, "_invoke_tools_parallel", new=AsyncMock(return_value=sql_only_res)):
            patch_empty = await agent.execute(base_state, config={})
        assert "retrieved_citations" not in patch_empty

        law_output = (
            "【法规库检索报告 - 「重复收费」 Top 1 条命中】\n"
            "1. [CITE:law_abcdef12] [来源: 行政法规/医疗保障基金使用监督管理条例.pdf | 第6页 | 哈希: 001122334455]\n"
            "   条文: 第十五条 定点医药机构不得分解住院。\n"
        )
        law_res = [({"id": "tc1", "name": "query_law_database"}, law_output)]
        with patch.object(agent, "_invoke_tools_parallel", new=AsyncMock(return_value=law_res)):
            patch_non_empty = await agent.execute(base_state, config={})
        assert len(patch_non_empty["retrieved_citations"]) == 1
        assert patch_non_empty["retrieved_citations"][0]["citation_id"] == "law_abcdef12"


@pytest.mark.asyncio
async def test_hub_merges_sql_auditor_and_policy_reviewer_citations():
    sql_cit = {
        "citation_id": "rag_sql11223",
        "source_type": "vector_rag",
        "source_doc": "指南.md",
        "content_hash": "1111aaaa2222",
    }
    policy_cit = {
        "citation_id": "law_pol44556",
        "source_type": "law_rag",
        "source_doc": "条例.pdf",
        "content_hash": "3333bbbb4444",
    }
    mock_coder = AsyncMock(
        return_value={
            "sql_query": "SELECT 1",
            "raw_data": json.dumps([{"psn_no": "P1", "medfee_sumamt": 500.0}]),
            "sql_validated": True,
            "retrieved_citations": [sql_cit],
        }
    )
    sql_agent = SQLAuditorSubagent(coder_executor=mock_coder)
    subtask = SubTaskSpec(subtask_id="st-1", focus_title="主表排查", query_instruction="查总额")
    artifact = await sql_agent.run_subtask(subtask, session_id="s-l2")
    assert artifact.retrieved_citations == [sql_cit]

    mock_sql_pool = AsyncMock()
    mock_sql_pool.run_parallel.return_value = [artifact]
    mock_policy = AsyncMock()
    mock_policy.review.return_value = ReviewVerdictArtifact(
        exemption_notes="无",
        statutory_citations=["第十五条"],
        citations_ledger=[policy_cit],
        risk_level="高",
        adjusted_summary="建议核查 [CITE:law_pol44556]。",
    )
    plan = OrchestrationPlan(
        tier=ExecutionTier.L2_MULTI_AGENT,
        reason="多维度复核",
        requires_graph=False,
        requires_policy_review=True,
        subtasks=[subtask],
    )
    hub = MultiAgentHubOrchestrator(sql_agent=mock_sql_pool, policy_agent=mock_policy)
    patch_out = await hub.execute_hub(
        {"session_id": "s-l2", "metadata": {"user_question": "排查重复住院", "execution_plan": plan.model_dump()}},
        config={},
    )
    ids = {c["citation_id"] for c in patch_out["retrieved_citations"]}
    assert ids == {"rag_sql11223", "law_pol44556"}
