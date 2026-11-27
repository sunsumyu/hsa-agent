"""
app/core/memory/hybrid_reranker.py
==================================
[Matt Pocock Deep Module] 记忆检索启发式混合精排与物理去重引擎

核心职责：
1. 启发式综合打分：深度融合归一化向量相似度、业务重要性权重、指数/双曲时间衰减与中英文硬匹配增益；
2. 实体哈希去重：消除重复记忆记录，仅保留最高分物理实例；
3. Top-N 预算自适应截断。
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, List, Set
from app.core.memory.base import MemoryItem


class HybridReranker:
    """记忆启发式混合精排深模块"""

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """将 str/dict/list 等多态记忆内容归一化为确定性文本，用于关键词匹配与哈希去重"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (dict, list)):
            try:
                return json.dumps(content, sort_keys=True, ensure_ascii=False)
            except TypeError:
                return str(content)
        return str(content)

    def rerank(
        self,
        query: str,
        candidates: List[MemoryItem],
        limit: int,
    ) -> List[MemoryItem]:
        """对候选记忆项目执行启发式精排与物理哈希去重"""
        if not candidates:
            return []

        scored_items = []
        now = datetime.now()
        query_keywords = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{3,}", query or ""))

        for item in candidates:
            # A. 基础分 (归一化相似度)
            base_score = getattr(item, "score", 0.5)

            # B. 业务重要性加权
            importance_boost = item.importance * 0.4

            # C. 时间双曲衰减
            delta_days = (now - item.timestamp).days if hasattr(item, "timestamp") else 0
            time_decay = 1.0 / (1.0 + 0.05 * delta_days)

            # D. 关键字硬匹配激励
            content_text = self._content_to_text(item.content)
            match_count = sum(1 for kw in query_keywords if kw in content_text)
            keyword_boost = min(match_count * 0.15, 0.3)

            final_score = (base_score * 0.3) + importance_boost + (time_decay * 0.1) + keyword_boost
            item.metadata["rerank_score"] = round(final_score, 4)
            scored_items.append((final_score, content_text, item))

        scored_items.sort(key=lambda x: x[0], reverse=True)

        # 物理哈希去重
        seen_content: Set[int] = set()
        unique_results: List[MemoryItem] = []
        for _, content_text, item in scored_items:
            content_hash = hash(content_text)
            if content_hash not in seen_content:
                unique_results.append(item)
                seen_content.add(content_hash)
            if len(unique_results) >= limit:
                break

        return unique_results

    def calculate_hybrid_score(self, item: MemoryItem) -> float:
        """核心评分函数：融合相似度、重要性加权与时间指数衰减"""
        # A. 基础相似度得分
        base_relevance = item.score if getattr(item, "score", 0) > 0 else 0.5

        # B. 重要性加权 [0.8, 1.2]
        importance_weight = 0.8 + (item.importance * 0.4)

        # C. 时间衰减 (Recency Bias: 指数衰减)
        age_days = (datetime.now() - item.timestamp).total_seconds() / (24 * 3600)
        recency_weight = math.exp(-0.05 * age_days)

        final_score = base_relevance * importance_weight * recency_weight
        return round(final_score, 4)


# 单例默认实例
hybrid_reranker = HybridReranker()
