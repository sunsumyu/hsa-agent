from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

from pydantic import BaseModel, Field

_CITE_TOKEN_RE = re.compile(r"\[CITE:([a-z]+_[a-f0-9]+)\]")
_FREEFORM_STATUTE_RE = re.compile(
    r"《(?P<title>[^》]{2,45})》"
    r"(?:（[^）]{1,25}）)?"
    r"(?P<article>第[一二三四五六七八九十百千0-9]+条(?:第[一二三四五六七八九十0-9]+款)?)?"
)
_DOC_EXT_RE = re.compile(r"\.(pdf|md|txt|docx?)$", re.IGNORECASE)
_REDACTED_TAG = "[已拦截未核验法规引用]"


class CitationGuardResult(BaseModel):
    """System 2 法条引文核验结果。"""

    passed: bool
    sanitized_text: str
    verified_ids: List[str] = Field(default_factory=list)
    blocked_citations: List[str] = Field(default_factory=list)


def _resolve_display_title(rec: Dict[str, Any]) -> str:
    """提取用于展示与核验对齐的法规标题，必要时回退至去扩展名的来源文件名。"""
    law_title = str(rec.get("law_title") or "").strip()
    if law_title:
        return law_title
    source_doc = str(rec.get("source_doc") or "").strip()
    if source_doc:
        base = source_doc.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        cleaned = _DOC_EXT_RE.sub("", base).strip()
        if cleaned:
            return cleaned
    return "法规条款"


def _format_authoritative_citation(rec: Dict[str, Any]) -> str:
    """将核验通过的引文记录格式化为带溯源锚点的权威引用。"""
    title = _resolve_display_title(rec)
    article = str(rec.get("article_num") or "").strip()
    page = f", 第{rec['page_num']}页" if rec.get("page_num") else ""
    origin = "向量库实查" if rec.get("source_type") in {"law_rag", "vector_rag"} else "规则库基准"
    return f"《{title}》{article}（[{origin}] 来源: {rec.get('source_doc', '')}{page}, ID: {rec['citation_id']}）"


def _resolve_cite_markers(
    text: str,
    ledger_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[str, Set[str], List[str]]:
    """展开合法的 [CITE:<id>] 锚点并拦截伪造锚点。"""
    verified: Set[str] = set()
    blocked: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        cid = match.group(1)
        rec = ledger_by_id.get(cid)
        if rec is None:
            blocked.append(f"[CITE:{cid}]")
            return _REDACTED_TAG
        verified.add(cid)
        return _format_authoritative_citation(rec)

    return _CITE_TOKEN_RE.sub(_replace, text), verified, blocked


def _record_matches_statute(rec: Dict[str, Any], title: str, article: str) -> bool:
    """判断自由文本法条引用是否与台账记录匹配。"""
    haystack = " ".join(
        str(rec.get(k) or "")
        for k in ("law_title", "source_doc", "section_path", "snippet")
    )
    display_title = _resolve_display_title(rec)
    if title != display_title and title not in haystack:
        return False
    if not article:
        return True
    art_haystack = " ".join(str(rec.get(k) or "") for k in ("article_num", "section_path", "snippet"))
    return article in art_haystack


def _audit_freeform_statutes(
    text: str,
    ledger: List[Dict[str, Any]],
    strict: bool,
) -> Tuple[str, Set[str], List[str]]:
    """逐条审计文本中的自由法条引用，未命中台账时记录并按 strict 策略拦截。"""
    verified: Set[str] = set()
    blocked: List[str] = []

    def _check(match: re.Match[str]) -> str:
        full = match.group(0)
        title = match.group("title").strip()
        article = (match.group("article") or "").strip()
        for rec in ledger:
            if _record_matches_statute(rec, title, article):
                if rec.get("citation_id"):
                    verified.add(str(rec["citation_id"]))
                return full
        blocked.append(full)
        return _REDACTED_TAG if strict else full

    return _FREEFORM_STATUTE_RE.sub(_check, text), verified, blocked


def enforce_citation_grounding(
    text: str,
    ledger: List[Dict[str, Any]],
    strict: bool = True,
) -> CitationGuardResult:
    """System 2 确定性法条引用门禁：反查合法 ID、拦截伪造 ID 与未召回的编造条款。"""
    if not text:
        return CitationGuardResult(passed=True, sanitized_text="")

    ledger_list = [r for r in (ledger or []) if isinstance(r, dict)]
    ledger_by_id = {str(r["citation_id"]): r for r in ledger_list if r.get("citation_id")}

    expanded_text, id_verified, id_blocked = _resolve_cite_markers(text, ledger_by_id)
    final_text, free_verified, free_blocked = _audit_freeform_statutes(
        expanded_text, ledger_list, strict=strict
    )

    all_blocked = id_blocked + free_blocked
    all_verified = sorted(id_verified | free_verified)
    return CitationGuardResult(
        passed=(len(all_blocked) == 0),
        sanitized_text=final_text,
        verified_ids=all_verified,
        blocked_citations=all_blocked,
    )
