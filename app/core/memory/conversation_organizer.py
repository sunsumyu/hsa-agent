"""
app/core/memory/conversation_organizer.py
=========================================
Three-stage conversation organizer separating noise/small-talk from substantive
topics and clustering interleaved multi-topic discussions:
  - L1: Deterministic noise vs. follow-up classification
  - L2: Compact PII-masked single-call LLM topic clustering (index mapping only)
  - L3: Deterministic full-coverage reconciliation & offline heuristic fallback
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field

from app.core.container import LazyProxy
from app.core.memory.pii_scrubber import pii_scrubber
from app.core.memory.session_title_generator import build_fallback_title, sanitize_title

_FOLLOWUP_CUES = (
    "继续", "展开", "详细", "再细一点", "还有呢", "为什么", "怎么算", "刚才",
    "上一轮", "第一家", "第二家", "前五", "具体明细", "怎么查", "下一步", "跳过", "补充",
)
_TOPIC_SWITCH_CUES = (
    "换个问题", "换一个问题", "另外", "顺便查一下", "再查一个",
    "切换场景", "还有一个问题", "另一个案件", "再问一个",
)
_NOISE_PATTERNS = (
    (re.compile(r"^(你好|您好|在吗|在不在|hi|hello|hey)[！!。,.~～?？]*$", re.IGNORECASE), "纯打招呼"),
    (re.compile(r"^(好的|好吧|收到|明白|了解|知道了|谢谢|多谢|感谢|辛苦了|ok|okay|thanks|嗯|哦|哈哈|再见|拜拜)[！!。,.~～]*$", re.IGNORECASE), "礼貌确认或结束语"),
    (re.compile(r"^(test|测试|1+|[?？!！.。]+)$", re.IGNORECASE), "无意义测试或符号输入"),
)
_COMPACT_PUNCT_RE = re.compile(r"[\s，。！？、,.!?~～…;；:：\"'`“”‘’()（）\[\]【】]+")
_ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_THOUGHT_TAG_RE = re.compile(r"<(?:thought|think)>.*?</(?:thought|think)>", re.IGNORECASE | re.DOTALL)

_ORGANIZE_SYSTEM_PROMPT = (
    "你是对话内容整理专家。给定一个多轮对话按轮次编号(turn_index 从 0 开始)的脱敏摘要，"
    "请完成以下整理并严格输出 JSON（禁止输出多余说明）：\n"
    "1. 将纯寒暄、客套确认（如你好/谢谢/收到/测试）放入 noise_turns，注意短句追问（如“继续”“第一家明细呢”）必须保留在对应主题中；\n"
    "2. 将实质讨论归并到 1..N 个主题（允许不连续的穿插轮次合并到同一主题）；\n"
    "3. 主题标题控制在 6-16 字且不得包含真实姓名、身份证或手机号，每个 turn_index 必须且只能出现一次。\n"
    "输出格式：\n"
    '{"topics": [{"title": "...", "domain": "audit|legal", "summary": "...", "turn_indices": [0, 1], "key_entities": ["..."]}], '
    '"noise_turns": [{"turn_index": 2, "reason": "..."}]}'
)


class TurnItem(BaseModel):
    """Atomic user-assistant turn indexed from 0."""

    turn_index: int
    user_message: str
    ai_message: str = ""


class TopicCluster(BaseModel):
    """Semantic topic cluster holding non-destructive turn index references."""

    topic_id: str
    title: str
    domain: str = "audit"
    summary: str = ""
    turn_indices: List[int] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)


class NoiseTurn(BaseModel):
    """Filtered small-talk or meaningless turn with human-readable reason."""

    turn_index: int
    reason: str = "闲聊或无实质内容"


class OrganizedSession(BaseModel):
    """Validated session topic/noise partition covering all turns 0..N-1."""

    topics: List[TopicCluster] = Field(default_factory=list)
    noise_turns: List[NoiseTurn] = Field(default_factory=list)
    mode: str = "heuristic"
    total_turns: int = 0


def _msg_role_and_content(msg: Any) -> Tuple[str, str]:
    if isinstance(msg, dict):
        role = str(msg.get("role") or msg.get("type") or "").lower()
        return role, str(msg.get("content") or "")
    role = str(getattr(msg, "type", "") or "").lower()
    return role, str(getattr(msg, "content", "") or "")


def extract_turns(messages: Sequence[Any]) -> List[TurnItem]:
    """Pair sequential human and AI messages into 0-based TurnItem objects."""
    turns: List[TurnItem] = []
    pending_user: Optional[str] = None
    for msg in messages:
        role, content = _msg_role_and_content(msg)
        if role in ("human", "user"):
            if pending_user is not None:
                turns.append(TurnItem(turn_index=len(turns), user_message=pending_user, ai_message=""))
            pending_user = content
        elif role in ("ai", "assistant"):
            if pending_user is not None:
                turns.append(TurnItem(turn_index=len(turns), user_message=pending_user, ai_message=content))
                pending_user = None
            elif turns:
                sep = "\n" if turns[-1].ai_message else ""
                turns[-1].ai_message = f"{turns[-1].ai_message}{sep}{content}"
    if pending_user is not None:
        turns.append(TurnItem(turn_index=len(turns), user_message=pending_user, ai_message=""))
    return turns


def classify_turn_l1(turn: TurnItem) -> Tuple[str, Optional[str]]:
    """Classify turn deterministically as 'noise', 'followup', or 'substantive'."""
    raw_text = (turn.user_message or "").strip()
    compact = _COMPACT_PUNCT_RE.sub("", raw_text)
    if not compact:
        return "noise", "空输入"
    for pattern, reason in _NOISE_PATTERNS:
        if pattern.match(compact):
            return "noise", reason
    has_followup = any(cue in compact for cue in _FOLLOWUP_CUES)
    has_switch = any(cue in compact for cue in _TOPIC_SWITCH_CUES)
    if has_followup and not has_switch and len(compact) <= 30:
        return "followup", None
    if len(compact) < 5:
        return "noise", "过短无实质内容"
    return "substantive", None


def _extract_semantic_tokens(text: str) -> Set[str]:
    """Extract ASCII tokens and CJK 2-grams for offline topic similarity."""
    cleaned = pii_scrubber.mask_sensitive_data(text or "")
    tokens: Set[str] = {tok.lower() for tok in _ASCII_TOKEN_RE.findall(cleaned)}
    for run in _CJK_RUN_RE.findall(cleaned):
        if len(run) == 2:
            tokens.add(run)
        else:
            for idx in range(len(run) - 1):
                tokens.add(run[idx : idx + 2])
    return tokens


def _jaccard_similarity(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _find_preceding_topic_pos(topics: List[Dict[str, Any]], turn_idx: int) -> int:
    best_pos, best_last_turn = -1, -1
    for pos, topic in enumerate(topics):
        prior = [idx for idx in topic["turn_indices"] if idx < turn_idx]
        if prior and max(prior) > best_last_turn:
            best_last_turn = max(prior)
            best_pos = pos
    if best_pos != -1:
        return best_pos
    return 0 if topics else -1


def _collect_noise_and_topics(
    raw_topics: Sequence[Any],
    raw_noise: Sequence[Any],
    l1_map: Dict[int, Tuple[str, Optional[str]]],
    total: int,
    default_domain: str,
) -> Tuple[Dict[int, str], List[Dict[str, Any]], Set[int]]:
    noise_map: Dict[int, str] = {}
    for item in raw_noise:
        idx = item.get("turn_index") if isinstance(item, dict) else getattr(item, "turn_index", None)
        reason = item.get("reason") if isinstance(item, dict) else getattr(item, "reason", None)
        if isinstance(idx, int) and 0 <= idx < total and l1_map[idx][0] != "followup":
            noise_map[idx] = str(reason or "闲聊或无实质内容")

    assigned: Set[int] = set(noise_map.keys())
    topics: List[Dict[str, Any]] = []
    for raw in raw_topics:
        data = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw or {})
        valid_indices: List[int] = []
        for idx in data.get("turn_indices") or []:
            if isinstance(idx, int) and 0 <= idx < total and idx not in assigned:
                assigned.add(idx)
                valid_indices.append(idx)
        if valid_indices:
            topics.append({
                "title": str(data.get("title") or ""),
                "domain": str(data.get("domain") or default_domain),
                "summary": str(data.get("summary") or ""),
                "turn_indices": valid_indices,
                "key_entities": list(data.get("key_entities") or [])[:6],
            })
    return noise_map, topics, assigned


def _assign_missing_turns(
    total: int,
    assigned: Set[int],
    l1_map: Dict[int, Tuple[str, Optional[str]]],
    noise_map: Dict[int, str],
    topics: List[Dict[str, Any]],
    default_domain: str,
) -> None:
    other_bucket: Optional[Dict[str, Any]] = None
    for idx in range(total):
        if idx in assigned:
            continue
        cls, reason = l1_map[idx]
        if cls == "noise":
            noise_map[idx] = reason or "闲聊或无实质内容"
            continue
        if cls == "followup":
            pos = _find_preceding_topic_pos(topics, idx)
            if pos >= 0:
                topics[pos]["turn_indices"].append(idx)
                continue
        if other_bucket is None:
            other_bucket = {
                "title": "", "domain": default_domain, "summary": "",
                "turn_indices": [], "key_entities": [],
            }
            topics.append(other_bucket)
        other_bucket["turn_indices"].append(idx)


def reconcile_organization(
    turns: Sequence[TurnItem],
    raw_topics: Sequence[Any],
    raw_noise: Sequence[Any],
    *,
    default_domain: str = "audit",
    mode: str = "llm",
) -> OrganizedSession:
    """Enforce exact 0..N-1 full coverage, protect follow-ups, and scrub PII."""
    total = len(turns)
    l1_map = {t.turn_index: classify_turn_l1(t) for t in turns}
    noise_map, topics, assigned = _collect_noise_and_topics(raw_topics, raw_noise, l1_map, total, default_domain)
    _assign_missing_turns(total, assigned, l1_map, noise_map, topics, default_domain)

    final_topics: List[TopicCluster] = []
    for idx, entry in enumerate(topics, 1):
        ordered_indices = sorted(set(entry["turn_indices"]))
        first_msg = turns[ordered_indices[0]].user_message
        clean_title = sanitize_title(entry["title"], max_len=20) or build_fallback_title(first_msg, default="未命名主题")
        clean_summary = pii_scrubber.mask_sensitive_data(entry["summary"]).strip()[:160]
        clean_entities = [pii_scrubber.mask_sensitive_data(str(e)).strip() for e in entry["key_entities"] if str(e).strip()]
        final_topics.append(TopicCluster(
            topic_id=f"topic-{idx}",
            title=clean_title,
            domain=entry["domain"] or default_domain,
            summary=clean_summary,
            turn_indices=ordered_indices,
            key_entities=clean_entities[:6],
        ))

    final_noise = [NoiseTurn(turn_index=k, reason=noise_map[k]) for k in sorted(noise_map)]
    return OrganizedSession(topics=final_topics, noise_turns=final_noise, mode=mode, total_turns=total)


def organize_heuristically(turns: Sequence[TurnItem], default_domain: str = "audit") -> OrganizedSession:
    """Offline deterministic clustering supporting noise separation and A->B->A merging."""
    topic_buckets: List[Dict[str, Any]] = []
    topic_tokens: List[Set[str]] = []
    noise_entries: List[Dict[str, Any]] = []

    for turn in turns:
        cls, reason = classify_turn_l1(turn)
        if cls == "noise":
            noise_entries.append({"turn_index": turn.turn_index, "reason": reason})
            continue
        if cls == "followup" and topic_buckets:
            topic_buckets[-1]["turn_indices"].append(turn.turn_index)
            continue
        cur_tokens = _extract_semantic_tokens(turn.user_message)
        explicit_switch = any(cue in (turn.user_message or "") for cue in _TOPIC_SWITCH_CUES)
        best_idx, best_score = -1, 0.0
        if not explicit_switch:
            for pos, tok_set in enumerate(topic_tokens):
                score = _jaccard_similarity(cur_tokens, tok_set)
                if score > best_score:
                    best_idx, best_score = pos, score
        if best_idx >= 0 and best_score >= 0.14:
            topic_buckets[best_idx]["turn_indices"].append(turn.turn_index)
            topic_tokens[best_idx] |= cur_tokens
        else:
            top_entities = [w for w, _ in Counter(cur_tokens).most_common(4)]
            topic_buckets.append({
                "title": build_fallback_title(turn.user_message, default="专项讨论"),
                "domain": default_domain,
                "summary": pii_scrubber.mask_sensitive_data(turn.user_message)[:120],
                "turn_indices": [turn.turn_index],
                "key_entities": top_entities,
            })
            topic_tokens.append(cur_tokens)

    return reconcile_organization(turns, topic_buckets, noise_entries, default_domain=default_domain, mode="heuristic")


def _parse_llm_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extract and repair JSON dictionary from LLM output safely."""
    cleaned = _THOUGHT_TAG_RE.sub("", raw_text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    snippet = cleaned[start : end + 1]
    try:
        parsed = json.loads(snippet)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        try:
            import json_repair

            repaired = json_repair.loads(snippet)
            return repaired if isinstance(repaired, dict) else None
        except Exception as exc:
            logger.debug(f"[ConversationOrganizer] JSON repair failed: {exc}")
            return None


def _build_turn_digest(turns: Sequence[TurnItem]) -> str:
    lines: List[str] = []
    for t in turns:
        safe_u = pii_scrubber.mask_sensitive_data(t.user_message or "").replace("\n", " ")[:150]
        safe_a = pii_scrubber.mask_sensitive_data(t.ai_message or "").replace("\n", " ")[:120]
        lines.append(f"[{t.turn_index}] 用户: {safe_u} | 助手: {safe_a or '无'}")
    return "\n".join(lines)


class ConversationOrganizer:
    """Three-stage session topic & noise organizer with offline heuristic fallback."""

    def __init__(self, llm_factory: Optional[Callable[[], object]] = None):
        self._llm_factory = llm_factory

    def _resolve_llm(self):
        if self._llm_factory is not None:
            return self._llm_factory()
        from app.infra.model_manager import model_manager

        llm, _ = model_manager.get_adaptive_llm(require_tools=False)
        return llm

    async def organize(
        self,
        messages: Sequence[Any],
        *,
        domain: str = "audit",
        timeout_seconds: float = 8.0,
    ) -> OrganizedSession:
        """Organize messages into reconciled topics and filtered noise turns."""
        turns = extract_turns(messages)
        if not turns:
            return OrganizedSession(topics=[], noise_turns=[], mode="heuristic", total_turns=0)

        digest = _build_turn_digest(turns)
        prompt = f"默认业务领域: {domain}\n总轮次: {len(turns)}\n{digest}"
        req_msgs = [SystemMessage(content=_ORGANIZE_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        try:
            llm = self._resolve_llm()
            response = await asyncio.wait_for(llm.ainvoke(req_msgs), timeout=timeout_seconds)
            parsed = _parse_llm_json(str(getattr(response, "content", response)))
            if parsed is None or (not parsed.get("topics") and not parsed.get("noise_turns")):
                return organize_heuristically(turns, default_domain=domain)
            return reconcile_organization(
                turns,
                parsed.get("topics") or [],
                parsed.get("noise_turns") or [],
                default_domain=domain,
                mode="llm",
            )
        except Exception as exc:
            logger.debug(f"[ConversationOrganizer] Falling back to heuristic organizer: {exc}")
            return organize_heuristically(turns, default_domain=domain)


conversation_organizer = LazyProxy("conversation_organizer")
