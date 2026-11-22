"""
app/agents/core_sql_resolver.py
=================================
[Matt Pocock Deep Module] 核心审计 SQL 仲裁解析器深模块

核心职责：
1. 从多轮历史累积 SQL 序列中智能筛选真正的核心业务审计 SQL。
2. 过滤并隔离 SELECT count(*) 等探针查询 (Probe Queries)。
3. 对包含聚合计算（SUM, AVG, MEDFEE, TOTAL, AMT, FEE 等）的核心度量查询享有优先选择权。
4. 提供极端情况下的全量保底策略。
"""

from __future__ import annotations
from typing import Sequence
from app.skills.security.probe_guard import is_probe_query


_METRIC_KEYWORDS = ("SUM(", "AVG(", "MEDFEE", "TOTAL", "AMT", "FEE", "ROUND(SUM")


def resolve_core_audit_sql(accumulated_sql_history: Sequence[str]) -> str:
    """
    从历史 SQL 序列中仲裁出主线审计 SQL。
    
    优先级：
    1. 包含业务度量与金额计算的非探针查询 (metric_queries 的最后一条)
    2. 任何非探针审计查询 (audit_queries 的最后一条)
    3. 全量历史查询的最后一条 (保底)
    """
    if not accumulated_sql_history:
        return ""

    audit_queries = [sql for sql in accumulated_sql_history if not is_probe_query(sql)]
    if not audit_queries:
        return accumulated_sql_history[-1]

    metric_queries = [
        s for s in audit_queries
        if any(m in s.upper() for m in _METRIC_KEYWORDS)
    ]
    if metric_queries:
        return metric_queries[-1]

    return audit_queries[-1]
