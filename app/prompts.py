"""
app.prompts — [重构] 代理到 app.core.prompt_registry
===========================================================
历史兼容层: 原来在此文件中硬编码的 Prompt 已迁移到 prompts/*.yaml。
所有导入路径保持不变 (from app.prompts import PLANNER_PROMPT ...),
内部代理到 PromptRegistry 实现版本化管理。

若 YAML 加载失败, PromptRegistry 会抛出异常; 由调用方决定如何降级。
"""

from __future__ import annotations
from loguru import logger

from app.core.prompt_registry import prompt_registry


def _load_prompt(prompt_id: str, fallback=None):
    """从 Registry 加载, 失败则使用 fallback。"""
    try:
        return prompt_registry.get(prompt_id)
    except Exception as e:
        logger.warning(f"[Prompts] Failed to load '{prompt_id}' from registry: {e}")
        if fallback is not None:
            return fallback
        raise


# ── Lazy-loaded module-level exports ──────────────────────────
# 这些常量会在首次 import 时从 YAML 加载。
# 若热更新 YAML, 需调用 prompt_registry.reload() 并重新 import。

PLANNER_PROMPT = _load_prompt("planner")
CODER_PROMPT = _load_prompt("coder")
ANALYST_PROMPT = _load_prompt("analyst")
REPORTER_PROMPT = _load_prompt("reporter")
CRITIC_PROMPT = _load_prompt("critic")
AUDITOR_PROMPT = _load_prompt("auditor")
CONCLUSION_PROMPT = _load_prompt("conclusion")


__all__ = [
    "PLANNER_PROMPT",
    "CODER_PROMPT",
    "ANALYST_PROMPT",
    "REPORTER_PROMPT",
    "CRITIC_PROMPT",
    "AUDITOR_PROMPT",
    "CONCLUSION_PROMPT",
]
