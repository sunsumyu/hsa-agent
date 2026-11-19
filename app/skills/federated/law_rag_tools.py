"""
app/skills/law_rag_tools.py
===========================
[V180.0] 法规知识库检索工具（对接 rag-pdf-project 法规 RAG 服务）

外部依赖：rag-pdf-project 的法规检索服务（FastAPI，默认 127.0.0.1:8765），
以 1819 部国家法律法规（宪法/法律/行政法规/司法解释）为语料，提供
TF-IDF + 语义(BGE) + 表格三路混合检索。服务地址经 LAW_RAG_BASE_URL 配置。

与内置 query_knowledge_base（语义记忆库）的区别：本工具检索的是**法规原文
条文库**，返回带 <分类>/<法规名> 与页码的条文出处，用于审计判定的政策对齐
依据（Policy Compliance）。二者互补：经验/政策解读查记忆库，法条原文查本库。
"""

import os
from typing import Optional

import httpx
from langchain_core.tools import tool
from loguru import logger

DEFAULT_LAW_RAG_URL = "http://127.0.0.1:8765"
CONTENT_MAX_CHARS = 600  # 单条条文截断，防止多命中撑爆 Agent Context

# 分类 → source 前缀过滤（法规库 chunk 的 source 形如 "法律/xxx.pdf"）
VALID_CATEGORIES = {"法律", "行政法规", "司法解释", "宪法"}

_http_client: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    """共享异步 HTTP 客户端（照 LLMFactory 连接池模式，复用长连接）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        )
    return _http_client


def _render_law_report(payload: dict, query: str, top_k: int) -> str:
    """把 /api/search 响应渲染为法规条文报告（对齐 render_rag_report 风格）"""
    text_hits = payload.get("text_results") or []
    table_hits = payload.get("table_results") or []

    if not text_hits and not table_hits:
        return (
            "🔍 [法规库] 未在法规库中找到相关条文。"
            "可尝试调整关键词（法条术语/条款编号），或指定分类重查："
            + "、".join(sorted(VALID_CATEGORIES))
            + "。"
        )

    lines = [f"【法规库检索报告 - 「{query}」 Top {min(top_k, len(text_hits))} 条命中】"]
    for i, hit in enumerate(text_hits, 1):
        source = hit.get("source", "Unknown")
        page = hit.get("page_num")
        page_note = f" | 第{page}页" if page else ""
        content = (hit.get("text") or "").strip()
        if len(content) > CONTENT_MAX_CHARS:
            content = content[:CONTENT_MAX_CHARS] + "…"
        lines.append(f"{i}. [来源: {source}{page_note}]\n   条文: {content}\n")

    for j, tb in enumerate(table_hits[:2], 1):
        header = (tb.get("header") or "").strip()
        source = tb.get("source", "Unknown")
        page = tb.get("page_num")
        page_note = f" | 第{page}页" if page else ""
        text = (tb.get("text") or "").strip()
        if len(text) > CONTENT_MAX_CHARS:
            text = text[:CONTENT_MAX_CHARS] + "…"
        lines.append(f"[表{j}] [来源: {source}{page_note} | 表头: {header}]\n   表格: {text}\n")

    lines.append("（引用上述条文时请标注法规名称与页码，作为审计判定的政策对齐依据）")
    return "\n".join(lines)


@tool
async def query_law_database(query: str, top_k: int = 5, category: Optional[str] = None) -> str:
    """
    [V180.0] 检索国家法律法规原文条文库（1819 部：宪法/法律/行政法规/司法解释）。
    当审计判定需要引用法律条文原文作为政策对齐依据（Policy Compliance）时必须调用此工具，
    例如：骗保处罚依据、基金使用监督管理条例条款、个人信息处理合规要求等。
    - query: 法规检索词（建议用法条术语/关键词，如"骗保 法律责任 处罚"）
    - category: 可选法规分类过滤，仅限：法律 / 行政法规 / 司法解释 / 宪法；不传则全库检索
    - top_k: 返回条文数，默认 5
    返回带法规名称与页码的条文出处，回答中引用时必须标注来源。
    """
    base_url = os.getenv("LAW_RAG_BASE_URL", DEFAULT_LAW_RAG_URL).rstrip("/")
    body: dict = {"query": query, "top_k": max(1, min(int(top_k), 20)), "mode": "hybrid"}
    if category and category.strip() in VALID_CATEGORIES:
        body["source"] = f"{category.strip()}/"
    elif category and category.strip():
        return (
            f"⚠️ [法规库] 无效分类「{category}」。可用分类："
            + "、".join(sorted(VALID_CATEGORIES))
            + "。"
        )

    try:
        resp = await _client().post(f"{base_url}/api/search", json=body)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.error(f"❌ [法规库] 检索服务调用失败: {e}")
        return (
            f"⚠️ [法规库] 检索服务不可达（{base_url}）：{e}。"
            "请确认法规 RAG 服务已启动（rag-pdf-project: python -m python.rpc_server.server，"
            "RAG_OUTPUT_DIR/RAG_INDEX_DIR 指向法规语料目录）。"
        )

    report = _render_law_report(payload, query, body["top_k"])
    logger.info(f"📖 [法规库] 「{query}」 命中报告已生成 ({len(report)} chars)")
    return report


async def get_law_rag_health() -> dict:
    """法规服务连通性探针（供系统配置/诊断页使用）"""
    base_url = os.getenv("LAW_RAG_BASE_URL", DEFAULT_LAW_RAG_URL).rstrip("/")
    try:
        resp = await _client().get(f"{base_url}/api/health", timeout=5.0)
        return {"url": base_url, "status": resp.json().get("status", "unknown")}
    except Exception as e:
        return {"url": base_url, "status": "unreachable", "error": str(e)}


__all__ = ["query_law_database", "get_law_rag_health"]
