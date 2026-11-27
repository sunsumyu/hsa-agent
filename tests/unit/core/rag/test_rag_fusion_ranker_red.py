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
    bm25_rank_hits,
    rrf_fuse_ranked_lists,
    rerank_hits_with_api_or_fallback,
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

    def test_bm25_rank_hits_exact_code_priority(self):
        generic = SimpleNamespace(
            content="关于医保药品超限使用的通用合规说明文档",
            score=0.95,
            metadata={"source": "a.md", "heading_path": "H1"}
        )
        exact = SimpleNamespace(
            content="编码 YB0102001 对应的药品仅限住院期间限工伤保险报销",
            score=0.60,
            metadata={"source": "b.md", "heading_path": "H2"}
        )
        ranked = bm25_rank_hits("YB0102001 报销限制", [generic, exact])
        assert ranked[0].metadata["heading_path"] == "H2"

    def test_rrf_fuse_ranked_lists_k60(self):
        doc_a = SimpleNamespace(content="条款A：重复收费", score=0.9, metadata={"heading_path": "A"})
        doc_b = SimpleNamespace(content="条款B：YB0102001 限门诊", score=0.7, metadata={"heading_path": "B"})
        doc_c = SimpleNamespace(content="条款C：分解住院", score=0.8, metadata={"heading_path": "C"})

        dense_list = [doc_a, doc_c, doc_b]  # doc_b 在 Dense 排第3
        bm25_list = [doc_b, doc_a]          # doc_b 在 BM25 排第1，doc_a 排第2

        # doc_a: 1/61 + 1/62; doc_b: 1/63 + 1/61; doc_c: 1/62
        fused = rrf_fuse_ranked_lists([dense_list, bm25_list], k=60, limit=2)
        assert len(fused) == 2
        assert fused[0].metadata["heading_path"] == "A"
        assert fused[1].metadata["heading_path"] == "B"
        assert fused[0].metadata["rrf_score"] > fused[1].metadata["rrf_score"]

    @pytest.mark.asyncio
    async def test_rerank_hits_fallback_when_no_api_url(self, monkeypatch):
        monkeypatch.delenv("RERANK_API_URL", raising=False)
        docs = [
            SimpleNamespace(content="d1", metadata={"heading_path": "1"}),
            SimpleNamespace(content="d2", metadata={"heading_path": "2"}),
            SimpleNamespace(content="d3", metadata={"heading_path": "3"}),
        ]
        res = await rerank_hits_with_api_or_fallback("query", docs, limit=2)
        assert [d.content for d in res] == ["d1", "d2"]

    @pytest.mark.asyncio
    async def test_rerank_hits_with_api_success_and_timeout_fallback(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        docs = [
            SimpleNamespace(content="d1", metadata={"heading_path": "1"}),
            SimpleNamespace(content="d2", metadata={"heading_path": "2"}),
        ]

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "results": [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.42},
            ]
        }
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        monkeypatch.setattr("httpx.AsyncClient", lambda timeout=0.5: mock_client)
        res = await rerank_hits_with_api_or_fallback(
            "query", docs, limit=2, api_url="https://api.example.com/v1/rerank"
        )
        assert [d.content for d in res] == ["d2", "d1"]
        assert res[0].metadata["rerank_score"] == 0.98

        # Timeout / error fallback
        mock_client.post = AsyncMock(side_effect=TimeoutError("timeout"))
        fallback = await rerank_hits_with_api_or_fallback(
            "query", docs, limit=2, api_url="https://api.example.com/v1/rerank"
        )
        assert [d.content for d in fallback] == ["d1", "d2"]
