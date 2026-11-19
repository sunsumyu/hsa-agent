"""
Red unit tests for rag_fusion_ranker deep module.
Tests:
- deduplicate_and_rank_hits (dedup by heading_path and prefix, pick highest score, top-k)
- render_rag_report (format results with source, path, content)
- extract_file_content (file reading fallback)
"""

import os
from types import SimpleNamespace
import pytest
from app.core.rag.rag_fusion_ranker import (
    deduplicate_and_rank_hits,
    render_rag_report,
    extract_file_content,
)


class TestRAGFusionRanker:
    def test_deduplicate_and_rank_hits(self):
        item1 = SimpleNamespace(
            content="这是一条审计规范文档内容",
            score=0.85,
            metadata={"source": "doc1.md", "heading_path": "H1/H2"}
        )
        item2 = SimpleNamespace(
            content="这是一条审计规范文档内容", # same prefix
            score=0.92,  # higher score
            metadata={"source": "doc1.md", "heading_path": "H1/H2"}
        )
        item3 = SimpleNamespace(
            content="另一条关于虚假住院的规则",
            score=0.70,
            metadata={"source": "doc2.md", "heading_path": "H1"}
        )

        ranked = deduplicate_and_rank_hits([item1, item2, item3], limit=2)
        assert len(ranked) == 2
        # item2 should win over item1 because of higher score
        assert ranked[0].score == 0.92
        assert ranked[1].score == 0.70

    def test_render_rag_report_empty(self):
        report = render_rag_report([], expansion_count=3)
        assert "未在知识库中找到相关合规性依据" in report

    def test_render_rag_report_formatted(self):
        item = SimpleNamespace(
            content="禁止对同一患者同日重复收取诊查费",
            score=0.95,
            metadata={"source": "国家医保飞检指引.pdf", "heading_path": "第三章/违规界定"}
        )
        report = render_rag_report([item], expansion_count=2)
        assert "基于 2 组查询扩展" in report
        assert "国家医保飞检指引.pdf" in report
        assert "第三章/违规界定" in report
        assert "禁止对同一患者同日重复收取诊查费" in report

    def test_extract_file_content_plain(self, tmp_path):
        test_file = tmp_path / "sample.txt"
        test_file.write_text("医保合规审计指引核心要点", encoding="utf-8")
        text = extract_file_content(str(test_file))
        assert "医保合规审计指引核心要点" in text

    def test_extract_file_content_nonexistent(self):
        assert extract_file_content("non_existent_file.xyz") == ""
