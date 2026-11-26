# tests/unit/rag/test_citation_ledger.py
from app.core.rag.citation_ledger import (
    CitationRecord,
    build_policy_registry_citations,
    make_citation_id,
    merge_citation_ledgers,
    parse_citations_from_tool_output,
)
from app.core.state_governance import build_initial_audit_state, create_turn_reset_patch


def test_make_citation_id_is_deterministic_and_prefixed():
    cid1 = make_citation_id("law_rag", "行政法规/条例.pdf", "第12页", "第十五条内容")
    cid2 = make_citation_id("law_rag", "行政法规/条例.pdf", "第12页", "第十五条内容")
    assert cid1 == cid2
    assert cid1.startswith("law_")
    assert len(cid1) == 12


def test_parse_citations_from_law_and_rag_tool_outputs():
    law_text = (
        "【法规库检索报告 - 「骗保」 Top 1 条命中】\n"
        "1. [CITE:law_11223344] [来源: 行政法规/医疗保障基金使用监督管理条例.pdf | 第5页 | 哈希: aabbccddeeff]\n"
        "   条文: 第十五条 定点医药机构不得分解住院。\n"
    )
    records = parse_citations_from_tool_output("query_law_database", law_text)
    assert len(records) == 1
    rec = records[0]
    assert rec.citation_id == "law_11223344"
    assert rec.source_type == "law_rag"
    assert rec.page_num == 5
    assert rec.article_num == "第十五条"
    assert rec.content_hash == "aabbccddeeff"

    rag_text = (
        "【RAG 专家检索报告 - 基于 1 组查询扩展】\n"
        "1. [CITE:rag_55667788] [来源: official_hsa_regulations_corpus.md] | [层级: 第一编 > 第三章] | [哈希: 112233445566]\n"
        "   内容: 《国家基本医疗保险用药管理暂行办法》第三十八条 严禁倒买倒卖。\n"
    )
    rag_recs = parse_citations_from_tool_output("query_knowledge_base", rag_text)
    assert len(rag_recs) == 1
    assert rag_recs[0].citation_id == "rag_55667788"
    assert rag_recs[0].source_type == "vector_rag"
    assert rag_recs[0].law_title == "国家基本医疗保险用药管理暂行办法"
    assert rag_recs[0].article_num == "第三十八条"


def test_merge_ledger_deduplicates_and_turn_reset_clears_citations():
    r1 = CitationRecord(
        citation_id="law_11223344",
        source_type="law_rag",
        source_doc="条例.pdf",
        snippet="第十五条",
    ).model_dump(mode="json")
    merged = merge_citation_ledgers([r1], [r1])
    assert len(merged) == 1

    init_state = build_initial_audit_state("测试", "sess-1")
    assert init_state["retrieved_citations"] == []

    reset_patch = create_turn_reset_patch({**init_state, "retrieved_citations": [r1]})
    assert reset_patch["retrieved_citations"] == []


def test_build_policy_registry_citations_parses_semicolon_entries():
    recs = build_policy_registry_citations(
        "《医疗保障基金使用监督管理条例》（国务院令第735号）第十五条；《中华人民共和国刑法》第二百六十六条"
    )
    assert len(recs) == 2
    assert recs[0].source_type == "policy_registry"
    assert recs[0].law_title == "医疗保障基金使用监督管理条例"
    assert recs[0].article_num == "第十五条"
