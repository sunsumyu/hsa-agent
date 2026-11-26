# tests/unit/rag/test_retrieval_citation_anchoring.py
import importlib
import sys
from types import SimpleNamespace

from app.core.rag.citation_ledger import parse_citations_from_tool_output
from app.core.rag.rag_fusion_ranker import render_rag_report
from app.skills.federated.law_rag_tools import _render_law_report


def test_render_rag_report_stamps_cite_id_and_round_trips():
    hit = SimpleNamespace(
        content="《医疗保障基金使用监督管理条例》第十五条 严禁分解住院。",
        metadata={"source": "official_hsa_regulations_corpus.md", "heading_path": "第一编 > 第三章"},
    )
    report = render_rag_report([hit], expansion_count=2)
    assert "[CITE:rag_" in report
    assert "[哈希:" in report

    parsed = parse_citations_from_tool_output("query_knowledge_base", report)
    assert len(parsed) == 1
    assert parsed[0].source_doc == "official_hsa_regulations_corpus.md"
    assert parsed[0].section_path == "第一编 > 第三章"
    assert parsed[0].article_num == "第十五条"


def test_render_law_report_stamps_cite_id_and_round_trips():
    payload = {
        "text_results": [
            {
                "source": "行政法规/医疗保障基金使用监督管理条例.pdf",
                "page_num": 8,
                "text": "第十九条 参保人员不得利用其享受医疗保障待遇的机会转卖药品。",
            }
        ],
        "table_results": [],
    }
    report = _render_law_report(payload, query="转卖药品", top_k=5)
    assert "[CITE:law_" in report
    assert "哈希:" in report

    parsed = parse_citations_from_tool_output("query_law_database", report)
    assert len(parsed) == 1
    assert parsed[0].page_num == 8
    assert parsed[0].article_num == "第十九条"
    assert parsed[0].law_title == "医疗保障基金使用监督管理条例"


def test_render_law_report_stamps_table_results_and_round_trips():
    payload = {
        "text_results": [],
        "table_results": [
            {
                "source": "行政法规/医疗保障基金使用监督管理条例.pdf",
                "page_num": 12,
                "header": "违规行为与处罚倍数",
                "text": "第三十八条 造成医保基金损失的，处1倍以上2倍以下罚款。",
            }
        ],
    }
    report = _render_law_report(payload, query="罚款倍数", top_k=5)
    assert "[表1] [CITE:law_" in report
    assert "表头: 违规行为与处罚倍数" in report
    assert "哈希:" in report

    parsed = parse_citations_from_tool_output("query_law_database", report)
    assert len(parsed) == 1
    assert parsed[0].page_num == 12
    assert parsed[0].article_num == "第三十八条"
    assert parsed[0].law_title == "医疗保障基金使用监督管理条例"


def test_build_chunk_record_enriches_metadata(monkeypatch, tmp_path):
    if "sentence_transformers" not in sys.modules:
        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            SimpleNamespace(SentenceTransformer=object),
        )
    module = importlib.import_module("scripts.chunk_and_ingest_corpus")
    record = module._build_chunk_record(
        filepath="data/knowledge_base/regulations/official_hsa_regulations_corpus.md",
        chunk_index=3,
        part="第一编 核心法规",
        chapter="第三章 监督管理",
        title="第十五条 分解住院",
        body_text="《医疗保障基金使用监督管理条例》第十五条 严禁定点医药机构分解住院、挂床住院。",
    )
    assert record["doc_id"] == "official_hsa_regulations_corpus"
    assert record["source"] == "official_hsa_regulations_corpus.md"
    assert record["chunk_index"] == 3
    assert record["heading_path"] == "第一编 核心法规 > 第三章 监督管理 > 第十五条 分解住院"
    assert record["law_title"] == "医疗保障基金使用监督管理条例"
    assert record["article_num"] == "第十五条"
    assert len(record["content_hash"]) == 12
    assert record["char_count"] == len(record["text"])

    corpus = tmp_path / "sample_regulation.md"
    corpus.write_text(
        "## 第一编\n### 第二章\n#### 第十九条 转卖药品\n"
        "《医疗保障基金使用监督管理条例》第十九条 参保人员不得利用其享受医疗保障待遇的机会转卖药品，接受返还现金或者实物。\n",
        encoding="utf-8",
    )
    chunks = module.perform_semantic_chunking(str(corpus))
    assert len(chunks) == 1
    assert chunks[0]["source"] == "sample_regulation.md"
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["article_num"] == "第十九条"
    assert chunks[0]["law_title"] == "医疗保障基金使用监督管理条例"
