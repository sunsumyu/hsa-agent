from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

SourceType = Literal["vector_rag", "law_rag", "policy_registry"]

_PREFIX_MAP: Dict[str, str] = {
    "law_rag": "law",
    "vector_rag": "rag",
    "policy_registry": "pol",
}

_LAW_BLOCK_RE = re.compile(
    r"\[CITE:(?P<cid>[a-z]+_[a-f0-9]+)\]\s*\[来源:\s*(?P<src>[^|\]]+)"
    r"(?:\s*\|\s*第(?P<page>\d+)页)?"
    r"(?:\s*\|\s*哈希:\s*(?P<chash>[a-f0-9]+))?[^\]]*\]\s*\n\s*(?:条文|表格):\s*(?P<body>.*?)"
    r"(?=\n\d+\.\s*\[CITE:|\n\[表\d+\]|\n（引用|\Z)",
    re.DOTALL,
)

_RAG_BLOCK_RE = re.compile(
    r"\[CITE:(?P<cid>[a-z]+_[a-f0-9]+)\]\s*\[来源:\s*(?P<src>[^\]]+)\]\s*\|\s*\[层级:\s*(?P<path>[^\]]+)\]"
    r"(?:\s*\|\s*\[哈希:\s*(?P<chash>[a-f0-9]+)\])?\s*\n\s*内容:\s*(?P<body>.*?)(?=\n\d+\.\s*\[CITE:|\Z)",
    re.DOTALL,
)

_LAW_TITLE_RE = re.compile(r"《([^》]{2,45})》")
_ARTICLE_NUM_RE = re.compile(r"(第[一二三四五六七八九十百千0-9]+条(?:第[一二三四五六七八九十0-9]+款)?)")


class CitationRecord(BaseModel):
    """结构化引文溯源记录。"""

    citation_id: str
    source_type: SourceType
    source_doc: str
    section_path: str = ""
    page_num: Optional[int] = None
    law_title: str = ""
    article_num: str = ""
    snippet: str = ""
    content_hash: str = ""


def make_content_hash(text: str) -> str:
    """计算片段文本的 12 位 SHA-256 摘要。"""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:12]


def make_citation_id(source_type: SourceType, source_doc: str, locator: str, snippet: str) -> str:
    """基于来源类型、文档、定位符与片段生成确定性引文 ID。"""
    prefix = _PREFIX_MAP.get(source_type, "ref")
    raw = f"{source_type}|{source_doc.strip()}|{locator.strip()}|{(snippet or '').strip()[:120]}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{digest}"


def extract_law_and_article(text: str, source_doc: str = "") -> Tuple[str, str]:
    """从条文正文或来源文件名提取法规名称与条号。"""
    title_match = _LAW_TITLE_RE.search(text or "")
    law_title = title_match.group(1).strip() if title_match else ""
    if not law_title and source_doc:
        base = source_doc.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        law_title = re.sub(r"\.(pdf|md|txt|docx?)$", "", base, flags=re.IGNORECASE).strip()
    art_match = _ARTICLE_NUM_RE.search(text or "")
    article_num = art_match.group(1).strip() if art_match else ""
    return law_title, article_num


def _parse_law_blocks(output_text: str) -> List[CitationRecord]:
    records: List[CitationRecord] = []
    for m in _LAW_BLOCK_RE.finditer(output_text):
        src = m.group("src").strip()
        body = m.group("body").strip()
        law_title, article_num = extract_law_and_article(body, src)
        records.append(
            CitationRecord(
                citation_id=m.group("cid"),
                source_type="law_rag",
                source_doc=src,
                page_num=int(m.group("page")) if m.group("page") else None,
                law_title=law_title,
                article_num=article_num,
                snippet=body[:300],
                content_hash=m.group("chash") or make_content_hash(body),
            )
        )
    return records


def _parse_rag_blocks(output_text: str) -> List[CitationRecord]:
    records: List[CitationRecord] = []
    for m in _RAG_BLOCK_RE.finditer(output_text):
        src = m.group("src").strip()
        path = m.group("path").strip()
        body = m.group("body").strip()
        law_title, article_num = extract_law_and_article(f"{path} {body}", src)
        records.append(
            CitationRecord(
                citation_id=m.group("cid"),
                source_type="vector_rag",
                source_doc=src,
                section_path=path,
                law_title=law_title,
                article_num=article_num,
                snippet=body[:300],
                content_hash=m.group("chash") or make_content_hash(body),
            )
        )
    return records


def parse_citations_from_tool_output(tool_name: str, output_text: str) -> List[CitationRecord]:
    """从 RAG / 法规检索工具返回文本中提取结构化溯源记录。"""
    if not output_text or "[CITE:" not in output_text:
        return []
    if tool_name == "query_law_database":
        return _parse_law_blocks(output_text)
    if tool_name in {"query_knowledge_base", "search_expert_knowledge"}:
        return _parse_rag_blocks(output_text)
    return _parse_law_blocks(output_text) or _parse_rag_blocks(output_text)


def build_policy_registry_citations(policy_basis: str) -> List[CitationRecord]:
    """将静态 policy_matcher / policy_registry 条文转为标准溯源记录。"""
    if not policy_basis:
        return []
    records: List[CitationRecord] = []
    for entry in re.split(r"[；;]+", policy_basis):
        text = entry.strip()
        if not text:
            continue
        law_title, article_num = extract_law_and_article(text)
        cid = make_citation_id("policy_registry", law_title or "policy_registry", article_num, text)
        records.append(
            CitationRecord(
                citation_id=cid,
                source_type="policy_registry",
                source_doc="configs/policy_registry.yaml",
                section_path=article_num,
                law_title=law_title,
                article_num=article_num,
                snippet=text[:300],
                content_hash=make_content_hash(text),
            )
        )
    return records


def merge_citation_ledgers(
    left: Optional[List[Dict[str, Any]]],
    right: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """按 citation_id 去重的 Append-Only 溯源账本合并器；支持空列表重置。"""
    if right is not None and len(right) == 0 and left:
        return []
    merged: Dict[str, Dict[str, Any]] = {}
    for item in (left or []) + (right or []):
        if isinstance(item, dict) and item.get("citation_id"):
            merged[item["citation_id"]] = item
    return list(merged.values())
