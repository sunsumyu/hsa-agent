"""
app/core/memory/session_title_generator.py
==========================================
Three-stage session title pipeline utilities:
  - T0: Instant PII-safe rule-based fallback title
  - T1: Async lightweight LLM title refinement with strict post-processing
"""

from __future__ import annotations

import asyncio
import re
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.core.memory.pii_scrubber import pii_scrubber

_GREETING_ONLY_RE = re.compile(
    r"^(你好|您好|在吗|在不在|hi|hello|hey|谢谢|多谢|测试|test|ok|okay|好的|嗯|哦|哈哈|再见|拜拜)[！!。,.~～?？]*$",
    re.IGNORECASE,
)
_LEADING_FILLER_RE = re.compile(
    r"^(?:你好|您好|请问|请帮我|帮我|麻烦帮我|麻烦|我想问一下|想问一下|请协助我|请帮忙)[，,、：:\s]*"
)
_THINK_BLOCK_RE = re.compile(r"<(?:thought|think)>.*?</(?:thought|think)>", re.IGNORECASE | re.DOTALL)
_RESIDUAL_TAG_RE = re.compile(r"</?(?:thought|think)>", re.IGNORECASE)
_TITLE_PREFIX_RE = re.compile(r"^(?:对话标题|会话标题|标题)\s*[:：]\s*")
_MARKDOWN_NOISE_RE = re.compile(r"[`#>~]+")
_MARKDOWN_EMPHASIS_RE = re.compile(r"(?<!\*)\*{1,2}([^*\n]+?)\*{1,2}(?!\*)")
_PUNCTUATION_STRIP_RE = re.compile(r"[\s，。！？、,.!?~～…;；:：\"'`“”‘’()（）\[\]【】]+")
_OUTER_PAIRS = ("\"\"", "''", "“”", "‘’", "《》", "「」", "『』", "【】", "``")
_QUOTE_CHARS = "\"'`“”‘’"
_TRAILING_PUNCT = "。！？，；：,.!?;:、"
_CLAUSE_BREAKS = "，。、；：,.;:"

_TITLE_SYSTEM_PROMPT = (
    "你是一个对话标题提炼器。请根据用户问题与助手回复，提炼一个简洁准确的中文会话标题。\n"
    "严格要求：\n"
    "1. 长度控制在 8 到 16 个汉字之间，概括核心业务实体或问题主题；\n"
    "2. 仅输出标题正文，禁止包含引号、书名号、序号、“标题：”前缀或任何解释说明；\n"
    "3. 禁止包含真实姓名、身份证号、手机号等敏感信息。"
)


def is_substantive_message(message: str) -> bool:
    """Return True when the message contains substantive intent beyond greetings."""
    if not message:
        return False
    compact = _PUNCTUATION_STRIP_RE.sub("", message).strip()
    if not compact or _GREETING_ONLY_RE.match(compact):
        return False
    return len(compact) >= 5


def _truncate_cleanly(text: str, max_len: int) -> str:
    """Truncate text cleanly at clause boundary when exceeding max_len."""
    if len(text) <= max_len:
        return text
    min_cut = max(max_len // 2, 1)
    for idx in range(max_len, min_cut - 1, -1):
        if text[idx - 1] in _CLAUSE_BREAKS:
            return text[: idx - 1].rstrip(_TRAILING_PUNCT).strip()
    return text[:max_len].rstrip(_TRAILING_PUNCT).strip()


def _strip_markdown_noise(text: str) -> str:
    """Remove markdown delimiters while preserving PII mask asterisks."""
    cleaned = _MARKDOWN_EMPHASIS_RE.sub(r"\1", text)
    return _MARKDOWN_NOISE_RE.sub(" ", cleaned)


def sanitize_title(raw_title: str, max_len: int = 20) -> str:
    """Mask PII, strip thought/markdown noise, remove wrappers, and truncate cleanly."""
    if not raw_title:
        return ""
    cleaned = pii_scrubber.mask_sensitive_data(str(raw_title))
    cleaned = _THINK_BLOCK_RE.sub(" ", cleaned)
    cleaned = _RESIDUAL_TAG_RE.sub(" ", cleaned)
    cleaned = _strip_markdown_noise(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _TITLE_PREFIX_RE.sub("", cleaned).rstrip(_TRAILING_PUNCT).strip()
    for open_ch, close_ch in _OUTER_PAIRS:
        while len(cleaned) >= 2 and cleaned.startswith(open_ch) and cleaned.endswith(close_ch):
            cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.strip(_QUOTE_CHARS).rstrip(_TRAILING_PUNCT).strip()
    return _truncate_cleanly(cleaned, max_len)


def build_fallback_title(user_message: str, max_len: int = 18, default: str = "新对话") -> str:
    """Build T0 instant rule-based fallback title with PII scrubbing."""
    if not is_substantive_message(user_message):
        return default
    masked = pii_scrubber.mask_sensitive_data(user_message)
    normalized = _strip_markdown_noise(masked)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for _ in range(3):
        updated = _LEADING_FILLER_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    cleaned = sanitize_title(normalized, max_len=max_len)
    return cleaned or default


class SessionTitleGenerator:
    """Async T1 LLM title generator with strict sanitization and timeout guard."""

    def __init__(self, llm_factory: Optional[Callable[[], object]] = None):
        self._llm_factory = llm_factory

    def _resolve_llm(self):
        if self._llm_factory is not None:
            return self._llm_factory()
        from app.infra.model_manager import model_manager

        llm, _ = model_manager.get_adaptive_llm(require_tools=False)
        return llm

    async def generate_llm_title(
        self,
        user_message: str,
        ai_reply: str = "",
        *,
        domain: str = "audit",
        timeout_seconds: float = 4.0,
    ) -> Optional[str]:
        """Refine a concise session title asynchronously with graceful fallback."""
        safe_user = pii_scrubber.mask_sensitive_data((user_message or "")[:300]).strip()
        if not safe_user:
            return None
        safe_ai = pii_scrubber.mask_sensitive_data((ai_reply or "")[:200]).strip()
        domain_label = "法律咨询与辩法" if domain == "legal" else "医保基金智能审计"
        prompt = f"业务领域: {domain_label}\n用户提问: {safe_user}\n助手首轮答复摘要: {safe_ai or '无'}"
        messages = [SystemMessage(content=_TITLE_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        try:
            llm = self._resolve_llm()
            response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout_seconds)
            raw_content = getattr(response, "content", response)
            cleaned = sanitize_title(str(raw_content), max_len=20)
            return cleaned if len(cleaned) >= 2 else None
        except Exception as exc:
            logger.debug(f"[SessionTitleGenerator] Async title refinement skipped: {exc}")
            return None


session_title_generator = SessionTitleGenerator()
