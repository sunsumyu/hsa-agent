"""
app/core/schema/scene_match_evaluator.py
========================================
[Matt Pocock Deep Module] 场景表关键词匹配与信息熵加权评估器

核心职责：
1. 关键词长短特异性信息熵加权：长度 >= 4 的长专有名词赋予长度权重，避免被通用短词稀释
2. 物理表名显式优先权：当用户在提问中显式写出物理表名时，赋予 +50 绝对优先提权
3. 领域原型 Archetype 增强融合：联动 ArchetypeRegistry 对业务场景追加加权
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from loguru import logger


class SceneMatchEvaluator:
    """场景表匹配打分策略深模块"""

    def evaluate(
        self,
        query: str,
        mapping: Dict[str, List[str]],
        archetype_registry: Optional[Any] = None,
    ) -> Dict[str, int]:
        """根据查询与场景映射计算各物理表的加权匹配分"""
        query_lower = query.lower()
        scores: Dict[str, int] = {}

        for table, keywords in mapping.items():
            score = 0
            for kw in keywords:
                if kw.lower() in query_lower:
                    # 特异性信息熵加权：长关键词信息量丰富，赋高权重
                    score += len(kw) if len(kw) >= 4 else 1

            # 显式物理表名包含，拥有绝对优先权
            if table.lower() in query_lower:
                score += 50

            if score > 0:
                scores[table] = score

        # 结合 Archetype 领域原型进行匹配加权
        if archetype_registry is None:
            try:
                from app.core.registry.archetype_registry import archetype_registry as _arch_reg
                archetype_registry = _arch_reg
            except Exception as e:
                logger.debug(f"[SceneMatchEvaluator] 获取默认 ArchetypeRegistry 跳过: {e}")
                archetype_registry = None

        if archetype_registry is not None and hasattr(archetype_registry, "match_archetypes"):
            try:
                for arch in archetype_registry.match_archetypes(query_lower):
                    for t in getattr(arch, "target_tables", []):
                        scores[t] = scores.get(t, 0) + 2
            except Exception as e:
                logger.debug(f"[SceneMatchEvaluator] 原型匹配加权跳过: {e}")

        return scores


# 单例默认实例
scene_match_evaluator = SceneMatchEvaluator()
