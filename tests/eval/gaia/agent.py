"""
Argus GAIA 推理适配器。

使用 GAIA 官方系统提示词 (`GAIA_SYSTEM_PROMPT`)，通过 Argus 模型工厂 (`model_manager`)
执行推理，并支持文本类附件内容注入与离线 Mock LLM 注入。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from tests.eval.gaia.dataset import GAIASample
from tests.eval.gaia.scorer import extract_final_answer

GAIA_SYSTEM_PROMPT = (
    "You are a general AI assistant. I will ask you a question. Report your thoughts, "
    "and finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER]. "
    "YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list "
    "of numbers and/or strings. If you are asked for a number, don't use comma to write your number "
    "neither use units such as $ or percent sign unless specified otherwise. If you are asked for "
    "a string, don't use articles, neither abbreviations (e.g. for cities), and write the digits in "
    "plain text unless specified otherwise. If you are asked for a comma separated list, apply the "
    "above rules depending of whether the element to be put in the list is a number or a string."
)

_TEXT_SUFFIXES = frozenset({".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".py", ".log"})


@dataclass
class GAIAAgentResult:
    predicted_answer: str
    raw_content: str = ""
    latency_ms: float = 0.0
    usage_metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _build_user_prompt(sample: GAIASample, max_attachment_chars: int = 8000) -> str:
    parts = [sample.question]
    if sample.file_name:
        if sample.file_path and sample.file_path.exists():
            suffix = sample.file_path.suffix.lower()
            if suffix in _TEXT_SUFFIXES:
                text = sample.file_path.read_text(encoding="utf-8", errors="replace")
                if len(text) > max_attachment_chars:
                    text = text[:max_attachment_chars] + "\n...[truncated]"
                parts.append(f"\n[Attachment: {sample.file_name}]\n{text}")
            else:
                parts.append(f"\n[Attachment available at: {sample.file_path} (type: {suffix})]")
        else:
            parts.append(f"\n[Referenced attachment: {sample.file_name}]")
    return "\n".join(parts)


class ArgusGAIAAgent:
    """使用 Argus 模型工厂执行 GAIA 评测。"""

    def __init__(
        self,
        model_id: str = "ppio-lightweight",
        llm: Optional[Any] = None,
        system_prompt: str = GAIA_SYSTEM_PROMPT,
    ):
        self.model_id = model_id
        self.system_prompt = system_prompt
        self._llm = llm

    def _get_llm(self) -> Any:
        if self._llm is not None:
            return self._llm

        from app.infra.model_manager import model_manager

        cfg = model_manager.providers.get(self.model_id)
        if cfg is None:
            available = sorted(model_manager.providers.keys())
            raise KeyError(
                f"未在 configs/llm_providers.json 中找到模型 `{self.model_id}`。可用: {available}"
            )
        llm = model_manager._create_llm(self.model_id, cfg)
        if llm is None:
            raise RuntimeError(
                f"模型 `{self.model_id}` 初始化失败，请检查对应的 API_KEY / BASE_URL 环境变量。"
            )
        self._llm = llm
        return llm

    async def predict(self, sample: GAIASample) -> GAIAAgentResult:
        llm = self._get_llm()
        messages: List[BaseMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=_build_user_prompt(sample)),
        ]

        t0 = time.perf_counter()
        try:
            response = await llm.ainvoke(messages)
            latency_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return GAIAAgentResult(
                predicted_answer="",
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        raw = response.content if isinstance(response.content, str) else str(response.content)
        ans = extract_final_answer(raw)
        usage = dict(getattr(response, "usage_metadata", None) or {})
        return GAIAAgentResult(
            predicted_answer=ans,
            raw_content=raw,
            latency_ms=latency_ms,
            usage_metadata=usage,
        )
