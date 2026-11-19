"""
app/core/schema/table_relation_linker.py
========================================
[Matt Pocock Deep Module] 表间拓扑关联图谱匹配与自动拉入链接器

核心职责：
1. 根据当前已决定的核心主表和用户提问意图，探测关联图谱中的 auto_pull 契约
2. 匹配关键词并自动拉入外键字典表（如机构字典表、行政区划表、药品目录表）
3. 提供表级引导提示语
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from loguru import logger


class TableRelationLinker:
    """表间拓扑关联拉入链接器深模块"""

    def resolve_related_tables(
        self,
        primary_table: str,
        user_query: str,
        relation_graph: Dict[str, Any],
    ) -> List[Tuple[str, str]]:
        """根据主表和用户查询，从关联图谱中解析需要级联拉入的关联字典表列表 [(table, hint)]"""
        if not relation_graph or primary_table not in relation_graph:
            return []

        graph_entry = relation_graph.get(primary_table, {})
        auto_pull = graph_entry.get("auto_pull", [])
        query_lower = user_query.lower()
        related: List[Tuple[str, str]] = []

        for entry in auto_pull:
            table = entry.get("table", "")
            keywords = entry.get("pull_keywords", [])
            hint = entry.get("hint", "")

            if any(kw.lower() in query_lower for kw in keywords):
                related.append((table, hint))
                logger.info(f"[TableRelationLinker] 关联表命中: {table}")

        return related


# 单例默认实例
table_relation_linker = TableRelationLinker()
