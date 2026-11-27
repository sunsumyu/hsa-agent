import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from app.core.state_governance import create_turn_reset_patch
from app.core.tool_engine.tool_evidence_extractor import ToolEvidenceExtractor
from app.multi_agent.contracts import ExecutionTier, OrchestrationPlan, SQLAuditArtifact, SubTaskSpec
from app.multi_agent.hub_orchestrator import MultiAgentHubOrchestrator
from app.multi_agent.policy_reviewer_agent import PolicyReviewerSubagent
from app.reporting.report_renderer import AuditReportRenderer
from app.reporting.reporter_node_orchestrator import orchestrate_reporter_node
from app.skills.federated.law_rag_tools import _render_law_report


def test_end_to_end_law_rag_to_report_zero_hallucination():
    law_payload = {
        "text_results": [
            {
                "source": "行政法规/医疗保障基金使用监督管理条例.pdf",
                "page_num": 12,
                "text": "第十九条 参保人员不得转卖医保药品。",
            }
        ],
        "table_results": [],
    }
    tool_output = _render_law_report(law_payload, query="转卖药品", top_k=5)
    processed = ToolEvidenceExtractor().process(
        results=[({"id": "tc1", "name": "query_law_database"}, tool_output)],
        state={"sql_history": [], "raw_data": "", "retrieved_citations": []},
    )
    assert len(processed.retrieved_citations) == 1
    cid = processed.retrieved_citations[0]["citation_id"]

    llm_draft = (
        f"核查确认存在倒药套现，依据 [CITE:{cid}] 应依法追缴；"
        "同时模型幻觉编造了 [CITE:law_00000000] 与《虚构医保处罚法》第七十七条。"
    )
    rendered = AuditReportRenderer().render(
        user_question="排查参保人倒卖医保药品行为",
        llm_conclusion=llm_draft,
        raw_data=[{"psn_no": "P1", "medfee_sumamt": 800.0}],
        sql_query="SELECT psn_no, medfee_sumamt FROM fqz_fymx_test",
        total_amount=800.0,
        finding_count=1,
        audit_metadata={"trace_id": "E2E-1", "retrieved_citations": processed.retrieved_citations},
    )

    assert "第十九条" in rendered.markdown
    assert "第12页" in rendered.markdown
    assert cid in rendered.markdown
    assert "law_00000000" not in rendered.markdown
    assert "《虚构医保处罚法》第七十七条" not in rendered.markdown
    assert rendered.audit_metadata["blocked_citation_count"] == 2
    assert rendered.audit_metadata["verified_citation_count"] >= 1


def test_turn_reset_prevents_turn1_citations_validating_turn2_hallucination():
    turn1_state = {
        "retrieved_citations": [
            {
                "citation_id": "law_aaaa1111",
                "source_type": "law_rag",
                "source_doc": "法律/中华人民共和国刑法.pdf",
                "law_title": "中华人民共和国刑法",
                "article_num": "第二百六十六条",
                "snippet": "第二百六十六条 诈骗公私财物...",
                "content_hash": "111122223333",
            }
        ],
        "metadata": {},
    }
    reset = create_turn_reset_patch(turn1_state)
    assert reset["retrieved_citations"] == []

    rendered = AuditReportRenderer().render(
        user_question="核查门诊退费冲正笔数",
        llm_conclusion="依据《中华人民共和国刑法》第二百六十六条移送司法。",
        raw_data=[{"psn_no": "P2", "det_item_fee_sumamt": -29.7}],
        sql_query="SELECT psn_no, det_item_fee_sumamt FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0",
        total_amount=-29.7,
        finding_count=1,
        audit_metadata={"trace_id": "E2E-2", "retrieved_citations": reset["retrieved_citations"]},
    )
    assert "《中华人民共和国刑法》第二百六十六条" not in rendered.markdown


@pytest.mark.asyncio
async def test_l2_multi_agent_rag_to_reporter_grounding_and_redaction(monkeypatch):
    hit = SimpleNamespace(
        content="《医疗保障基金使用监督管理条例》第十五条 严禁定点医药机构分解住院。",
        metadata={"source": "official_hsa_regulations_corpus.md", "heading_path": "第三章 监督管理"},
        score=0.95,
    )
    monkeypatch.setenv("RERANK_API_URL", "")
    monkeypatch.setattr("app.core.rag.tool.memory_hub.semantic.recall", AsyncMock(return_value=[hit]))

    async def fake_llm(role, messages, tools=None, **kwargs):
        if tools:
            return AIMessage(content="", tool_calls=[{"id": "tc-rag", "name": "query_knowledge_base", "args": {"query": "分解住院"}}])
        m = re.search(r"\[CITE:(rag_[a-f0-9]+)\]", str(messages[-1].content))
        assert m is not None
        return AIMessage(content=f"核查确认存在分解住院违规，依据 [CITE:{m.group(1)}] 应予核减；模型幻觉 [CITE:rag_deadbeef] 与《虚构L2医保法》第九十条。\n【风险等级】：高")

    sql_mock = AsyncMock()
    sql_mock.run_parallel.return_value = [
        SQLAuditArtifact(subtask_id="s1", focus_title="分解住院核查", sql_query="SELECT psn_no, medfee_sumamt FROM fqz_fymx_test", raw_data='[{"psn_no": "P9", "medfee_sumamt": 1500.0}]', row_count=1, total_amount=1500.0, validated=True)
    ]
    plan = OrchestrationPlan(tier=ExecutionTier.L2_MULTI_AGENT, requires_graph=False, requires_policy_review=True, subtasks=[SubTaskSpec(subtask_id="s1", focus_title="分解住院核查", query_instruction="排查分解住院")], reason="l2-e2e")
    hub = MultiAgentHubOrchestrator(graph_agent=AsyncMock(), sql_agent=sql_mock, policy_agent=PolicyReviewerSubagent(llm_caller=fake_llm))
    state = {"session_id": "s-l2-e2e", "current_turn_query": "排查分解住院", "metadata": {"user_question": "排查分解住院", "execution_plan": plan.model_dump()}}

    hub_patch = await hub.execute_hub(state, config={})
    result = await orchestrate_reporter_node({**state, **hub_patch}, config={}, max_retries=1)
    report = result["structured_report"]
    assert "[向量库实查]" in report.markdown
    assert "第十五条" in report.markdown
    assert "official_hsa_regulations_corpus.md" in report.markdown
    assert "rag_deadbeef" not in report.markdown
    assert "《虚构L2医保法》第九十条" not in report.markdown
    assert "[已拦截未核验法规引用]" in report.markdown
    assert report.audit_metadata["blocked_citation_count"] == 2
    assert report.audit_metadata["verified_citation_count"] >= 1
    assert result["retrieved_citations"] == []
