"""
Red unit tests for markdown_chunker deep module.
Tests:
- split_paragraphs_with_headings
- chunk_paragraphs
- preprocess_markdown_for_embedding
- approx_token_len
"""

import pytest
from app.core.memory.markdown_chunker import (
    split_paragraphs_with_headings,
    chunk_paragraphs,
    preprocess_markdown_for_embedding,
    approx_token_len,
)


class TestMarkdownChunker:
    def test_approx_token_len(self):
        # Empty string
        assert approx_token_len("") == 0
        # Chinese characters: 4 chars * 1.5 = 6
        assert approx_token_len("医保审计") == 6
        # English: 4 chars * 0.4 = 1.6 -> 1
        assert approx_token_len("test") == 1

    def test_preprocess_markdown_for_embedding(self):
        raw = "## 标题\n![image](http://example.com/pic.png)\n这是一个 [链接](http://a.com) **加粗** 和 <i>HTML</i>"
        cleaned = preprocess_markdown_for_embedding(raw)
        assert "http" not in cleaned
        assert "<i>" not in cleaned
        assert "**" not in cleaned
        assert "链接" in cleaned
        assert "加粗" in cleaned

    def test_split_paragraphs_with_headings(self):
        doc = """# 第一章 概述
这是概述正文第一段。

这是概述正文第二段。

## 1.1 违规定义
这是定义正文。
"""
        paras = split_paragraphs_with_headings(doc)
        assert len(paras) == 3
        assert paras[0]["heading_path"] == "第一章 概述"
        assert "这是概述正文第一段" in paras[0]["content"]
        assert paras[1]["heading_path"] == "第一章 概述"
        assert paras[2]["heading_path"] == "第一章 概述 > 1.1 违规定义"
        assert "这是定义正文" in paras[2]["content"]

    def test_chunk_paragraphs(self):
        paras = [
            {"content": "段落一" * 20, "heading_path": "H1"},
            {"content": "段落二" * 20, "heading_path": "H1 > H2"},
            {"content": "段落三" * 20, "heading_path": "H1 > H2"},
        ]
        chunks = chunk_paragraphs(paras, chunk_tokens=50, overlap_tokens=10)
        assert len(chunks) >= 2
        for ch in chunks:
            assert "content" in ch
            assert "heading_path" in ch
            assert "tokens" in ch
