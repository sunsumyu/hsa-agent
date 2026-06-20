"""
app/tools/pipeline_tools.py
============================
[V178.10] 管线追踪 MCP 工具 — 供 Artifact 看板调用。

提供 get_snapshot 工具，返回管线执行状态快照。
"""

from __future__ import annotations

import json
from typing import Dict, Any, Optional


def get_snapshot(session_id: str = "", last_n: int = 50) -> Dict[str, Any]:
    """
    获取管线执行状态快照。

    Args:
        session_id: 会话 ID（空字符串表示最新会话）
        last_n: 返回最近 N 条事件

    Returns:
        包含事件列表、节点统计、SQL 历史的字典
    """
    from app.core.pipeline_tracker import pipeline_tracker
    return pipeline_tracker.get_snapshot(session_id, last_n)
