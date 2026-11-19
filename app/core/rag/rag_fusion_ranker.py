"""
app/core/rag/rag_fusion_ranker.py
=================================
RAG 多路召回融合、去重排序与结果渲染深模块（Deep Module）

职责：
- 基于路径与内容特征的候选集聚合与去重（保留高 score 项）
- 命中文档降序排序与 top-k 截断
- 检索报告文本结构化渲染（来源、层级、内容标注）
- 多模态文档内容提取与 fallback 读取
"""

from __future__ import annotations

import os
from typing import List, Dict, Any
from loguru import logger


def deduplicate_and_rank_hits(hits: List[Any], limit: int = 5) -> List[Any]:
    """
    对多路召回的候选文档项进行基于标题路径与内容特征的去重，
    若重复则保留最高分项，最后按 score 降序排序并截断至 limit。
    """
    if not hits:
        return []

    agg_results: Dict[str, Any] = {}
    for item in hits:
        metadata = getattr(item, "metadata", {}) or {}
        heading_path = metadata.get("heading_path", "")
        content = getattr(item, "content", "") or ""
        score = getattr(item, "score", 0.0)

        uid = f"{heading_path}_{content[:50]}"
        if uid not in agg_results or score > getattr(agg_results[uid], "score", 0.0):
            agg_results[uid] = item

    sorted_hits = sorted(
        agg_results.values(),
        key=lambda x: getattr(x, "score", 0.0),
        reverse=True
    )
    return sorted_hits[:limit]


def render_rag_report(sorted_hits: List[Any], expansion_count: int = 1) -> str:
    """
    将排序后的 RAG 命中项渲染为结构化报告。
    """
    if not sorted_hits:
        return "🔍 [RAG] 未在知识库中找到相关合规性依据。"

    formatted = [f"【RAG 专家检索报告 - 基于 {expansion_count} 组查询扩展】"]
    for i, item in enumerate(sorted_hits, 1):
        metadata = getattr(item, "metadata", {}) or {}
        source = metadata.get("source", "Unknown")
        path = metadata.get("heading_path", "ROOT")
        content = getattr(item, "content", "")
        content_str = content.strip() if isinstance(content, str) else str(content)
        formatted.append(f"{i}. [来源: {source}] | [层级: {path}]\n   内容: {content_str}\n")

    return "\n".join(formatted)


def extract_file_content(path: str) -> str:
    """
    从指定文件提取文本内容，优先使用 MarkItDown 解析，失败则降级为普通 UTF-8 文本读取。
    """
    if not path or not os.path.exists(path):
        return ""

    # 尝试使用 MarkItDown
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(path)
        content = getattr(result, "text_content", "")
        if content:
            return content
    except Exception:
        pass

    # Fallback: 基础文件读取
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[RAGFileExtractor] 读取文件失败 {path}: {e}")
        return ""
