"""
Semantic HyDE Generator Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates hypothetical document
expansion, domain prompt construction, and graceful fallback behind an async interface.
"""
from typing import Any, Optional
from loguru import logger


class SemanticHydeGenerator:
    """HyDE (Hypothetical Document Embeddings) 假设性审计业务描述生成器"""

    @staticmethod
    async def generate_hyde_context(query: str, config: Any = None) -> str:
        """
        [V175.0] HyDE 核心：生成假设性审计上下文。
        将用户的口语化提问转化为专业、具体的审计业务描述。
        """
        if not query or not query.strip():
            return ""

        from app.core.llm_provider import llm_provider

        hyde_prompt = [
            (
                "system",
                "你是一位资深的医保审计专家。请针对用户的问题，生成一段专业的审计口径描述。内容应包含可能涉及的物理指标（如金额、天数、频次）和逻辑特征，字数在 100 字以内。",
            ),
            ("human", f"审计任务：{query}"),
        ]

        try:
            # 使用 LIGHT 模型快速生成，避免延迟
            response = await llm_provider.chat(
                role="planner_light",
                messages=hyde_prompt,
                config=config,
            )
            return str(getattr(response, "content", "") or "")
        except Exception as e:
            logger.warning(f"HyDE 生成失败: {e}，安全降级")
            return ""
