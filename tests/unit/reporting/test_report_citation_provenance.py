"""
tests/unit/reporting/test_report_citation_provenance.py
======================================================
TDD tests for Task 5: System 2 citation guardrail, Chapter 1 origin tagging,
and Chapter 6 citation provenance table in reporting pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.reporting.report_renderer import AuditReportRenderer
from app.reporting.reporter_node_orchestrator import orchestrate_reporter_node
from app.reporting.traceability_section_builder import build_traceability_section


def test_renderer_renders_vector_provenance_table_and_blocks_hallucinated_clause():
    renderer = AuditReportRenderer()
    vector_ledger = [
        {
            "citation_id": "law_55aa66bb",
            "source_type": "law_rag",
            "source_doc": "行政法规/医疗保障基金使用监督管理条例.pdf",
            "section_path": "第三章",
            "page_num": 5,
            "law_title": "医疗保障基金使用监督管理条例",
            "article_num": "第十五条",
            "snippet": "第十五条 严禁分解住院。",
            "content_hash": "deadbeef1234",
        }
    ]
    report = renderer.render(
        user_question="排查分解住院违规",
        llm_conclusion="依据 [CITE:law_55aa66bb] 存在违规，另触犯《虚假医保特别法》第九十九条。",
        raw_data=[{"psn_no": "P1", "medfee_sumamt": 1200.0}],
        sql_query="SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql",
        total_amount=1200.0,
        finding_count=1,
        audit_metadata={"trace_id": "TR-1", "retrieved_citations": vector_ledger},
    )

    assert "[向量库实查]" in report.markdown
    assert "law_55aa66bb" in report.markdown
    assert "deadbeef1234" in report.markdown
    assert "《虚假医保特别法》第九十九条" not in report.markdown
    assert "[已拦截未核验法规引用]" in report.markdown
    assert "| Citation ID | 来源类型 | 文档 / 页码 / 章节 | 内容哈希 |" in report.markdown
    assert report.audit_metadata["verified_citation_count"] == 1
    assert report.audit_metadata["blocked_citation_count"] == 1


def test_renderer_static_fallback_tags_and_preserves_matched_policies():
    renderer = AuditReportRenderer()
    caller_meta = {"trace_id": "TR-STATIC"}
    report = renderer.render(
        user_question="排查进销存库存倒挂",
        llm_conclusion="依据《医疗保障基金使用监督管理条例》（国务院令第735号）第十五条核查，发现异常 1 例。",
        raw_data=[{"psn_no": "P2", "medfee_sumamt": 800.0}],
        sql_query="SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql",
        total_amount=800.0,
        finding_count=1,
        audit_metadata=caller_meta,
    )

    assert "[静态规则兜底]" in report.markdown
    assert "[向量库实查]" not in report.markdown
    assert "《医疗保障基金使用监督管理条例》（国务院令第735号）第十五条" in report.markdown
    assert "[已拦截未核验法规引用]" not in report.markdown
    assert report.audit_metadata["blocked_citation_count"] == 0
    assert report.audit_metadata["verified_citation_count"] >= 1
    assert caller_meta == {"trace_id": "TR-STATIC"}


def test_traceability_section_renders_provenance_table_and_empty_safe():
    assert build_traceability_section(None) == ""
    assert build_traceability_section({}) == ""

    md = build_traceability_section(
        {
            "trace_id": "TR-1",
            "retrieved_citations": [
                {
                    "citation_id": "rag_11223344",
                    "source_type": "vector_rag",
                    "source_doc": "专家指南/核查规范.md",
                    "section_path": "第二节",
                    "content_hash": "abcd9876",
                }
            ],
        }
    )
    assert "| Citation ID | 来源类型 | 文档 / 页码 / 章节 | 内容哈希 |" in md
    assert "`rag_11223344`" in md
    assert "`abcd9876`" in md


@pytest.mark.asyncio
async def test_orchestrator_forwards_retrieved_citations_without_mutating_ai_kwargs():
    ai_kwargs = {"source": "ClickHouse"}
    last_ai = AIMessage(content="SQL已执行", additional_kwargs=ai_kwargs)
    retrieved = [
        {
            "citation_id": "law_55aa66bb",
            "source_type": "law_rag",
            "source_doc": "条例.pdf",
            "content_hash": "deadbeef1234",
        }
    ]
    state = {
        "raw_data": '[{"psn_no": "P001", "medfee_sumamt": 1500.0}]',
        "sql_query": "SELECT * FROM fqz_fymx_test",
        "sql_history": ["SELECT * FROM fqz_fymx_test"],
        "methodology": "频次核查",
        "metadata": {"user_question": "排查分解住院"},
        "messages": [last_ai],
        "retrieved_citations": retrieved,
    }

    with patch("app.reporting.reporter_node_orchestrator.resolve_conclusion", new_callable=AsyncMock) as mock_resolve, \
         patch("app.reporting.report_renderer.AuditReportRenderer.render") as mock_render, \
         patch("app.core.booster.PrecisionBooster.verify_semantic_alignment") as mock_booster:
        mock_resolve.return_value = ("发现异常 1 例", False)
        mock_report = MagicMock()
        mock_report.markdown = "## 医保专项稽核报告"
        mock_render.return_value = mock_report
        mock_booster.return_value = (True, "")

        await orchestrate_reporter_node(state, config={}, max_retries=1)

        passed_meta = mock_render.call_args.kwargs["audit_metadata"]
        assert passed_meta["source"] == "ClickHouse"
        assert passed_meta["retrieved_citations"] == retrieved
        assert ai_kwargs == {"source": "ClickHouse"}


def test_traceability_provenance_table_escapes_pipe_in_all_cells():
    md = build_traceability_section(
        {
            "trace_id": "TR-PIPE",
            "retrieved_citations": [
                {
                    "citation_id": "law|fake_id",
                    "source_type": "custom|type",
                    "source_doc": "法规|文档.pdf",
                    "section_path": "第一章|第一节",
                    "content_hash": "hash|1234",
                }
            ],
        }
    )
    row_line = next(line for line in md.splitlines() if "fake_id" in line)
    assert "`law\\|fake_id`" in row_line
    assert "custom\\|type" in row_line
    assert "法规\\|文档.pdf / 第一章\\|第一节" in row_line
    assert "`hash\\|1234`" in row_line


@pytest.mark.asyncio
async def test_orchestrator_persists_sanitized_conclusion_in_turn_commit():
    retrieved = [
        {
            "citation_id": "law_55aa66bb",
            "source_type": "law_rag",
            "source_doc": "行政法规/医疗保障基金使用监督管理条例.pdf",
            "section_path": "第三章",
            "page_num": 5,
            "law_title": "医疗保障基金使用监督管理条例",
            "article_num": "第十五条",
            "snippet": "第十五条 严禁分解住院。",
            "content_hash": "deadbeef1234",
        }
    ]
    state = {
        "raw_data": '[{"psn_no": "P001", "medfee_sumamt": 1500.0}]',
        "sql_query": "SELECT psn_no, medfee_sumamt FROM fqz_fymx_test",
        "sql_history": ["SELECT psn_no, medfee_sumamt FROM fqz_fymx_test"],
        "methodology": "频次核查",
        "metadata": {"user_question": "排查分解住院"},
        "messages": [AIMessage(content="SQL已执行")],
        "retrieved_citations": retrieved,
    }
    hallucinated_conclusion = (
        "依据 [CITE:law_55aa66bb] 发现异常，同时触犯 [CITE:FAKE_99] 与《虚假医保特别法》第九十九条。"
    )

    with patch("app.reporting.reporter_node_orchestrator.resolve_conclusion", new_callable=AsyncMock) as mock_resolve, \
         patch("app.core.booster.PrecisionBooster.verify_semantic_alignment") as mock_booster:
        mock_resolve.return_value = (hallucinated_conclusion, False)
        mock_booster.return_value = (True, "")

        res = await orchestrate_reporter_node(state, config={}, max_retries=1)

    persisted_summary = res["accumulated_findings"][-1]["summary_conclusion"]
    assert "FAKE_99" not in persisted_summary
    assert "虚假医保特别法" not in persisted_summary
    assert "[已拦截未核验法规引用]" in persisted_summary
    assert "《医疗保障基金使用监督管理条例》第十五条" in persisted_summary

    booster_conclusion = mock_booster.call_args.args[1]
    assert "FAKE_99" not in booster_conclusion
    assert "虚假医保特别法" not in booster_conclusion
