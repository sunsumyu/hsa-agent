"""
domains/legal/agents/llm_client.py
==================================
法律智能体统一 LLM 调用封装（委托至项目 model_manager 算力池）。
提供超时保护、结构化 JSON 提取、Token 用量采集与优雅降级能力：
当无可用模型或调用异常时返回 None，由上层 Agent 自动回退至确定性规则。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional, Tuple
from loguru import logger


def _extract_json_block(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_usage(response: Any, model_id: str) -> Dict[str, Any]:
    meta = getattr(response, "usage_metadata", None) or {}
    if isinstance(meta, dict):
        prompt = int(meta.get("input_tokens", 0) or meta.get("prompt_tokens", 0) or 0)
        completion = int(meta.get("output_tokens", 0) or meta.get("completion_tokens", 0) or 0)
    else:
        prompt, completion = 0, 0
    return {"model_id": model_id, "prompt": prompt, "completion": completion}


async def ainvoke_legal_json(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: float = 25.0,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """调用 LLM 并解析为 JSON dict；失败返回 (None, {})。"""
    text, usage = await ainvoke_legal_text(system_prompt, user_prompt, timeout=timeout)
    if not text:
        return None, usage
    parsed = _extract_json_block(text)
    if parsed is None:
        logger.warning("[LegalLLM] 响应未能解析为合法 JSON，将触发确定性回退")
    return parsed, usage


async def ainvoke_legal_text(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: float = 25.0,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """调用 LLM 并返回纯文本及用量元数据；失败返回 (None, {})。"""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.infra.model_manager import model_manager

        llm = None
        model_id = "unknown"
        for req_tools in (True, False):
            try:
                llm, model_id = model_manager.get_adaptive_llm(require_tools=req_tools)
                if llm is not None:
                    break
            except Exception:
                continue
        if llm is None:
            return None, {}

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
        content = getattr(resp, "content", "")
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        text = str(content).strip()
        usage = _extract_usage(resp, model_id)
        return (text or None), usage
    except Exception as e:
        logger.warning(f"[LegalLLM] 调用异常，已安全回退: {e}")
        return None, {}
