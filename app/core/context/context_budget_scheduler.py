"""
app/core/context/context_budget_scheduler.py
============================================
[Matt Pocock Deep Module] 上下文预算贪心调度与弹性降级决策器

核心职责：
1. 区分高优先级关键指令/便签与普通候选信息包，确保核心证据绝对占位
2. 结合 Jaccard 词法相似度与指数时间衰减新近度对普通信息包加权评分
3. 在 Token 预算边界内执行贪心装载，并在预算超限时触发 ClickHouse Schema 弹性向 Header-Only 降级
"""

from __future__ import annotations

import math
import datetime
from typing import Any, List, Optional
from loguru import logger

from app.core.context.turn_history_compactor import estimate_tokens


class ContextBudgetScheduler:
    """上下文信息包预算调度与弹性精选器深模块"""

    def __init__(self, config: Optional[Any] = None):
        self.config = config

    def _calculate_jaccard(self, text: str, query: str) -> float:
        """计算候选文本与用户查询的词法 Jaccard 相似度"""
        w_text = set(text.lower().split())
        w_query = set(query.lower().split())
        if not w_query:
            return 0.0
        return len(w_text & w_query) / len(w_text | w_query)

    def _calculate_time_decay(self, timestamp: datetime.datetime) -> float:
        """计算候选信息包的时间衰减权重"""
        age_hours = (datetime.datetime.now() - timestamp).total_seconds() / 3600
        decay_factor = 0.1
        return max(0.1, min(1.0, math.exp(-decay_factor * age_hours)))

    def schedule(
        self,
        packets: List[Any],
        query: str,
        budget: int,
        schema_selector: Optional[Any] = None,
    ) -> List[Any]:
        """在 Token 预算限制内执行评分排序、过滤与贪心精选"""
        high_priority = [p for p in packets if p.metadata.get("priority") == "high"]
        evaluate_pool = [p for p in packets if p.metadata.get("priority") != "high"]

        high_tokens = sum(p.token_count for p in high_priority)
        remaining_budget = budget - high_tokens

        if remaining_budget <= 0:
            logger.warning("🚨 [ContextBudgetScheduler] 高优先级指令/便签已满额物理预算！")
            return high_priority

        relevance_weight = getattr(self.config, "relevance_weight", 0.7)
        recency_weight = getattr(self.config, "recency_weight", 0.3)
        min_relevance = getattr(self.config, "min_relevance", 0.15)

        scored_pool = []
        for p in evaluate_pool:
            if p.relevance_score is None:
                p.relevance_score = self._calculate_jaccard(p.content, query)
            rel = p.relevance_score
            rec = self._calculate_time_decay(p.timestamp)

            combined = relevance_weight * rel + recency_weight * rec

            if rel >= min_relevance or p.metadata.get("type") == "clickhouse_schema":
                scored_pool.append((combined, p))

        # 降序排列
        scored_pool.sort(key=lambda x: x[0], reverse=True)

        selected = high_priority.copy()
        current_tokens = high_tokens

        for _, p in scored_pool:
            if current_tokens + p.token_count <= budget:
                selected.append(p)
                current_tokens += p.token_count
            else:
                # 触发 ClickHouse 表结构的弹性退化降级机制
                if p.metadata.get("type") == "clickhouse_schema" and schema_selector is not None:
                    try:
                        from app.core.registry.schema_registry import schema_registry
                        entry = schema_registry.get_table(p.metadata.get("table_name", ""))
                        if entry:
                            header_xml = schema_selector.schema_to_header_only(entry)
                            header_t = estimate_tokens(header_xml)
                            if current_tokens + header_t <= budget:
                                from app.core.context.context_builder import ContextPacket
                                selected.append(ContextPacket(
                                    content=header_xml,
                                    relevance_score=p.relevance_score,
                                    metadata=p.metadata
                                ))
                                current_tokens += header_t
                    except Exception as schema_degrade_err:
                        logger.warning(f"Schema 降级处理失败: {schema_degrade_err}")
                else:
                    break

        return selected


# 单例默认实例
context_budget_scheduler = ContextBudgetScheduler()
