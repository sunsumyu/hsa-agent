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

import math
import os
import re
from collections import Counter
from typing import List, Dict, Any, Optional
from loguru import logger


def _build_hit_uid(item: Any) -> str:
    """生成用于多路去重与 RRF 聚合的稳定文档标识。"""
    metadata = getattr(item, "metadata", {}) or {}
    heading_path = metadata.get("heading_path", "")
    content = getattr(item, "content", "") or ""
    return f"{heading_path}_{content[:50]}"


def _tokenize_for_bm25(text: str) -> List[str]:
    """轻量中英文混合分词：保留医保/药品编码与英文单词，中文采用双字切分+单字兜底。"""
    if not text:
        return []
    lower = text.lower()
    tokens: List[str] = re.findall(r"[a-z0-9][a-z0-9._-]*", lower)
    for segment in re.findall(r"[\u4e00-\u9fa5]+", lower):
        if len(segment) == 1:
            tokens.append(segment)
        else:
            tokens.extend(segment[i : i + 2] for i in range(len(segment) - 1))
            tokens.extend(segment)
    return tokens


def bm25_rank_hits(
    query: str,
    hits: List[Any],
    k1: float = 1.5,
    b: float = 0.75,
) -> List[Any]:
    """
    对候选文档集合执行 Okapi BM25 稀疏打分排序，弥补向量检索对医保编码与专有名词的不敏感。
    """
    if not hits or not query:
        return list(hits)

    unique_docs: Dict[str, Any] = {}
    for item in hits:
        uid = _build_hit_uid(item)
        if uid not in unique_docs:
            unique_docs[uid] = item

    docs_list = list(unique_docs.values())
    tokenized_docs = [
        _tokenize_for_bm25(str(getattr(doc, "content", "") or ""))
        for doc in docs_list
    ]
    n_docs = len(docs_list)
    avgdl = sum(len(t) for t in tokenized_docs) / max(n_docs, 1)

    df: Counter = Counter()
    doc_tfs: List[Counter] = []
    for tokens in tokenized_docs:
        tf = Counter(tokens)
        doc_tfs.append(tf)
        for term in tf:
            df[term] += 1

    query_tokens = _tokenize_for_bm25(query)
    scored: List[tuple[float, Any]] = []
    for doc, tokens, tf in zip(docs_list, tokenized_docs, doc_tfs):
        dl = len(tokens)
        score = 0.0
        for q_term in query_tokens:
            if q_term not in tf:
                continue
            freq = tf[q_term]
            doc_freq = df[q_term]
            idf = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
            denom = freq + k1 * (1.0 - b + b * (dl / max(avgdl, 1.0)))
            score += idf * (freq * (k1 + 1.0)) / max(denom, 1e-9)
        scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in scored]


def rrf_fuse_ranked_lists(
    ranked_lists: List[List[Any]],
    k: int = 60,
    limit: int = 20,
) -> List[Any]:
    """
    倒数秩融合 (Reciprocal Rank Fusion, RRF)。
    公式: RRF_Score(d) = sum(1 / (k + rank_i(d)))，摆脱多路通道分值尺度差异。
    """
    if not ranked_lists or limit <= 0:
        return []

    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Any] = {}

    for hits in ranked_lists:
        if not hits:
            continue
        seen_in_list = set()
        for rank, item in enumerate(hits, start=1):
            uid = _build_hit_uid(item)
            if uid in seen_in_list:
                continue
            seen_in_list.add(uid)
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + 1.0 / (k + rank)
            if uid not in doc_map:
                doc_map[uid] = item

    sorted_uids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)[:limit]
    fused: List[Any] = []
    for uid in sorted_uids:
        doc = doc_map[uid]
        meta = getattr(doc, "metadata", None)
        if isinstance(meta, dict):
            meta["rrf_score"] = round(rrf_scores[uid], 6)
        fused.append(doc)
    return fused


async def rerank_hits_with_api_or_fallback(
    query: str,
    candidates: List[Any],
    limit: int = 5,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 0.5,
) -> List[Any]:
    """
    精排阶段：优先调用线上 Cross-Encoder Rerank API；未配置或超时/异常时平滑降级为 RRF 顺序。
    """
    if not candidates or limit <= 0:
        return []

    target_url = (api_url if api_url is not None else os.getenv("RERANK_API_URL", "")).strip()
    if not target_url:
        return candidates[:limit]

    target_key = (api_key if api_key is not None else os.getenv("RERANK_API_KEY", "")).strip()
    target_model = (model if model is not None else os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")).strip()

    headers = {"Content-Type": "application/json"}
    if target_key:
        headers["Authorization"] = f"Bearer {target_key}"

    payload = {
        "model": target_model,
        "query": query,
        "documents": [str(getattr(c, "content", "") or "") for c in candidates],
        "top_n": min(limit, len(candidates)),
    }

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(target_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results") or []
        if not results:
            logger.warning("[RerankAPI] 响应缺少 results 字段，降级使用 RRF 排序结果")
            return candidates[:limit]

        ranked: List[Any] = []
        for entry in sorted(results, key=lambda r: float(r.get("relevance_score", 0.0)), reverse=True):
            idx = entry.get("index")
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                item = candidates[idx]
                meta = getattr(item, "metadata", None)
                if isinstance(meta, dict):
                    meta["rerank_score"] = round(float(entry.get("relevance_score", 0.0)), 6)
                ranked.append(item)
            if len(ranked) >= limit:
                break

        return ranked or candidates[:limit]
    except Exception as e:
        logger.warning(f"⚠️ [RerankAPI] 线上精排调用失败或超时 ({e})，自动降级至 RRF 排序")
        return candidates[:limit]


def deduplicate_and_rank_hits(hits: List[Any], limit: int = 5) -> List[Any]:
    """
    对多路召回的候选文档项进行基于标题路径与内容特征的去重，
    若重复则保留最高分项，最后按 score 降序排序并截断至 limit。
    """
    if not hits:
        return []

    agg_results: Dict[str, Any] = {}
    for item in hits:
        score = getattr(item, "score", 0.0)
        uid = _build_hit_uid(item)
        if uid not in agg_results or score > getattr(agg_results[uid], "score", 0.0):
            agg_results[uid] = item

    sorted_hits = sorted(
        agg_results.values(),
        key=lambda x: getattr(x, "score", 0.0),
        reverse=True
    )
    return sorted_hits[:limit]


def render_rag_report(sorted_hits: List[Any], expansion_count: int = 1) -> str:
    """将排序后的 RAG 命中项渲染为带确定性 [CITE:<id>] 锚点的结构化报告。"""
    if not sorted_hits:
        return "🔍 [RAG] 未在知识库中找到相关合规性依据。"

    from app.core.rag.citation_ledger import make_citation_id, make_content_hash

    formatted = [f"【RAG 专家检索报告 - 基于 {expansion_count} 组查询扩展】"]
    for i, item in enumerate(sorted_hits, 1):
        metadata = getattr(item, "metadata", {}) or {}
        source = str(metadata.get("source", "Unknown"))
        path = str(metadata.get("heading_path", "ROOT"))
        content = getattr(item, "content", "")
        content_str = content.strip() if isinstance(content, str) else str(content)
        cid = str(metadata.get("citation_id") or make_citation_id("vector_rag", source, path, content_str))
        chash = str(metadata.get("content_hash") or make_content_hash(content_str))
        formatted.append(
            f"{i}. [CITE:{cid}] [来源: {source}] | [层级: {path}] | [哈希: {chash}]\n   内容: {content_str}\n"
        )

    formatted.append("（引用上述条文时请标注 [CITE:xxx] 编号与来源，严禁编造未召回条款）")
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
    except Exception as exc:
        logger.debug(f"[RAGFusionRanker] MarkItDown parse fallback for {path}: {exc}")

    # Fallback: 基础文件读取
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[RAGFileExtractor] 读取文件失败 {path}: {e}")
        return ""
