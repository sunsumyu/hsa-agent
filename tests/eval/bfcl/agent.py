"""
Argus 原生 Function Calling 适配器。

通过 Argus 的 `model_manager._create_llm` + `bind_tools` 发起原生工具调用，
同时支持注入 Mock LLM 以便离线单元测试。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from tests.eval.bfcl.dataset import BFCLSample
from tests.eval.bfcl.schema import to_openai_tools

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert assistant with access to tools. "
    "When a user request can be fulfilled by calling one or more of the provided functions, "
    "emit the exact tool call(s) with accurate arguments. "
    "If none of the provided functions is relevant or sufficient to answer the request, "
    "do NOT call any function and reply directly in plain text."
)


@dataclass
class AgentCallResult:
    tool_calls: List[Dict[str, Any]]
    raw_content: str = ""
    latency_ms: float = 0.0
    usage_metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _to_langchain_messages(
    turns: List[Dict[str, str]],
    system_prompt: Optional[str] = DEFAULT_SYSTEM_PROMPT,
) -> List[BaseMessage]:
    msgs: List[BaseMessage] = []
    has_system = any(m.get("role") == "system" for m in turns)
    if system_prompt and not has_system:
        msgs.append(SystemMessage(content=system_prompt))

    for m in turns:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            msgs.append(SystemMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(HumanMessage(content=content))
    return msgs


class ArgusFCAgent:
    """使用 Argus 模型工厂执行 BFCL 原生 Function Calling。"""

    def __init__(
        self,
        model_id: str = "ppio-lightweight",
        llm: Optional[Any] = None,
        system_prompt: Optional[str] = DEFAULT_SYSTEM_PROMPT,
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

    async def predict(self, sample: BFCLSample) -> AgentCallResult:
        """对单条 BFCL 样本发起模型调用并提取标准化 tool_calls。"""
        llm = self._get_llm()
        tools, name_map = to_openai_tools(sample.function)
        messages = _to_langchain_messages(sample.first_turn_messages, self.system_prompt)

        bound = llm.bind_tools(tools) if tools else llm
        t0 = time.perf_counter()
        try:
            response = await bound.ainvoke(messages)
            latency_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return AgentCallResult(
                tool_calls=[],
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        extracted: List[Dict[str, Any]] = []
        for tc in getattr(response, "tool_calls", None) or []:
            safe_name = tc.get("name", "")
            orig_name = name_map.get(safe_name, safe_name)
            args = tc.get("args") or {}
            extracted.append({"name": orig_name, "arguments": dict(args)})

        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        usage = dict(getattr(response, "usage_metadata", None) or {})
        return AgentCallResult(
            tool_calls=extracted,
            raw_content=raw_content,
            latency_ms=latency_ms,
            usage_metadata=usage,
        )
