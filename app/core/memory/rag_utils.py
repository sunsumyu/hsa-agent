"""
app/core/memory/rag_utils.py
===========================
[V4.6] 企业级 RAG 核心算法库
支持标题路径感知分割与 CJK Token 精准估算
"""

import re
from typing import List, Optional
from loguru import logger

# 重新导出纯文本算法深模块，保持 100% 向后兼容
from app.core.memory.markdown_chunker import (
    split_paragraphs_with_headings,
    chunk_paragraphs,
    preprocess_markdown_for_embedding,
    approx_token_len,
)


async def generate_mqe_queries(query: str, n: int = 3) -> List[str]:
    """
    [V4.6] MQE：生成多样化的审计查询扩展
    """
    from app.core.llm_provider import llm_provider
    try:
        prompt = [
            ("system", f"你是一位医保审计专家。请针对用户的原始查询，生成 {n} 个语义等价但表述不同的专业审计查询。要求：使用中文，简短专业，涵盖可能的业务别名。"),
            ("human", f"原始查询：{query}"),
        ]
        response = await llm_provider.chat(role="planner_light", messages=prompt)
        text = str(response.content)
        lines = [re.sub(r'^\d+\.\s*', '', ln.strip("- \t")) for ln in text.splitlines()]
        return [ln for ln in lines if ln][:n]
    except Exception as e:
        logger.warning(f"MQE 扩展失败: {e}")
        return []


async def generate_hyde_document(query: str) -> Optional[str]:
    """
    [V4.6] HyDE：生成假设性审计证据段落
    """
    from app.core.llm_provider import llm_provider
    try:
        prompt = [
            ("system", "根据用户提出的审计问题，先写一段可能的违规事实描述或政策条文原文（不要包含分析过程），用于向量检索。"),
            ("human", f"问题：{query}\n请直接输出一段客观、包含关键术语的专业段落。"),
        ]
        response = await llm_provider.chat(role="coder_light", messages=prompt)
        return str(response.content)
    except Exception as e:
        logger.warning(f"HyDE 生成失败: {e}")
        return None
