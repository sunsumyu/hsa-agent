"""
app/core/pipeline_tracker.py
=============================
[V178.10] 管线执行追踪器 — 双写到日志文件 + 内存缓冲，供 Artifact 看板消费。

职责：
  1. 每个 LangGraph 节点开始/结束时记录状态快照
  2. 追踪 sql_history 的增量变化
  3. 双写：(a) JSONL 日志文件 (b) 内存事件缓冲
  4. 提供 get_snapshot() 供 Artifact 看板拉取

使用方式：
  from app.core.pipeline_tracker import pipeline_tracker

  # 在节点开始时
  pipeline_tracker.on_node_start("SQLEXEC", state)

  # 在节点结束时
  pipeline_tracker.on_node_end("SQLEXEC", state, result_dict)
"""

from __future__ import annotations

import json
import time
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from loguru import logger


@dataclass
class PipelineEvent:
    """单次管线事件"""
    event_type: str          # "node_start" | "node_end" | "state_update"
    node: str                # 节点名 (PLANNER / ALIGNER / SQLEXEC / CRITIC / REPORTER / CONSOLIDATOR)
    timestamp: float         # Unix timestamp
    timestamp_iso: str       # ISO 格式时间
    session_id: str          # 会话 ID
    elapsed_ms: int = 0      # 节点耗时（仅 node_end）
    # 状态快照
    sql_query: str = ""
    sql_history: List[str] = field(default_factory=list)
    raw_data_preview: str = ""
    retry_count: int = 0
    error_log: str = ""
    # 结果摘要
    result_summary: str = ""
    # 附加信息
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineTracker:
    """
    管线执行追踪器 — 线程安全，双写到日志文件 + 内存缓冲。
    """

    def __init__(self, log_dir: str = "logs/pipeline"):
        self._events: List[PipelineEvent] = []
        self._lock = threading.Lock()
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_session: str = ""
        self._node_start_times: Dict[str, float] = {}
        # 日志文件路径：每次新会话创建新文件
        self._log_file: Optional[Path] = None

    def _get_log_file(self, session_id: str) -> Path:
        """获取当前会话的日志文件路径"""
        if not self._log_file or self._current_session != session_id:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_id = session_id.replace("/", "_").replace("\\", "_")[:40]
            self._log_file = self._log_dir / f"pipeline_{safe_id}_{ts}.jsonl"
            self._current_session = session_id
        return self._log_file

    def _write_event(self, event: PipelineEvent):
        """将事件双写到日志文件 + 内存缓冲"""
        # 1. 写入内存缓冲
        with self._lock:
            self._events.append(event)
            # 保留最近 500 条事件，防止内存泄漏
            if len(self._events) > 500:
                self._events = self._events[-500:]

        # 2. 写入 JSONL 日志文件
        try:
            log_path = self._get_log_file(event.session_id)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.warning(f"[PipelineTracker] 日志写入失败: {e}")

    def on_node_start(self, node: str, state: Dict[str, Any]):
        """记录节点开始事件"""
        session_id = state.get("session_id", "unknown")
        now = time.time()
        self._node_start_times[f"{session_id}:{node}"] = now

        event = PipelineEvent(
            event_type="node_start",
            node=node,
            timestamp=now,
            timestamp_iso=datetime.fromtimestamp(now).isoformat(),
            session_id=session_id,
            sql_query=_truncate(state.get("sql_query", ""), 200),
            sql_history=state.get("sql_history", []),
            raw_data_preview=_truncate(state.get("raw_data", ""), 200),
            retry_count=state.get("retry_count", 0),
            error_log=state.get("error_log") or "",
        )
        self._write_event(event)
        logger.info(f"📍 [Pipeline] → {node} started | sql_history={len(state.get('sql_history', []))} items")

    def on_node_end(self, node: str, state: Dict[str, Any], result: Optional[Dict[str, Any]] = None):
        """记录节点结束事件"""
        session_id = state.get("session_id", "unknown")
        now = time.time()

        # 计算节点耗时
        start_key = f"{session_id}:{node}"
        start_time = self._node_start_times.pop(start_key, now)
        elapsed_ms = int((now - start_time) * 1000)

        # 合并 result 中的更新字段
        sql_history = (result or {}).get("sql_history") or state.get("sql_history", [])
        sql_query = (result or {}).get("sql_query") or state.get("sql_query", "")
        raw_data = (result or {}).get("raw_data") or state.get("raw_data", "")
        error_log = (result or {}).get("error_log") or state.get("error_log") or ""

        # 生成结果摘要
        result_summary = ""
        if result:
            parts = []
            if result.get("sql_query"):
                parts.append(f"SQL: {_truncate(result['sql_query'], 60)}")
            if result.get("raw_data"):
                data_preview = _truncate(result["raw_data"], 80)
                parts.append(f"Data: {data_preview}")
            if result.get("error_log"):
                parts.append(f"Error: {_truncate(result['error_log'], 60)}")
            result_summary = " | ".join(parts)

        event = PipelineEvent(
            event_type="node_end",
            node=node,
            timestamp=now,
            timestamp_iso=datetime.fromtimestamp(now).isoformat(),
            session_id=session_id,
            elapsed_ms=elapsed_ms,
            sql_query=_truncate(sql_query, 200),
            sql_history=sql_history if isinstance(sql_history, list) else [],
            raw_data_preview=_truncate(raw_data, 200),
            retry_count=state.get("retry_count", 0),
            error_log=error_log or "",
            result_summary=result_summary,
        )
        self._write_event(event)
        logger.info(f"📍 [Pipeline] ← {node} ended | {elapsed_ms}ms | sql_history={len(sql_history)} items")

    def on_state_update(self, node: str, state: Dict[str, Any], description: str = ""):
        """记录状态更新事件（如路由决策、质量门控结果等）"""
        session_id = state.get("session_id", "unknown")
        now = time.time()

        event = PipelineEvent(
            event_type="state_update",
            node=node,
            timestamp=now,
            timestamp_iso=datetime.fromtimestamp(now).isoformat(),
            session_id=session_id,
            sql_query=_truncate(state.get("sql_query", ""), 200),
            sql_history=state.get("sql_history", []),
            raw_data_preview=_truncate(state.get("raw_data", ""), 200),
            retry_count=state.get("retry_count", 0),
            error_log=state.get("error_log") or "",
            result_summary=description,
        )
        self._write_event(event)

    def get_snapshot(self, session_id: str = "", last_n: int = 50) -> Dict[str, Any]:
        """
        获取管线状态快照，供 Artifact 看板消费。

        Returns:
            {
                "events": [...],       # 最近 N 条事件
                "current_sql_history": [...],  # 当前 sql_history
                "current_sql_query": "...",
                "total_events": int,
                "session_id": "...",
            }
        """
        with self._lock:
            events = list(self._events)

        # 按会话过滤
        if session_id:
            events = [e for e in events if e.session_id == session_id]

        # 最近 N 条
        recent = events[-last_n:]

        # 当前状态（取最后一次 node_end 的值）
        current_sql_history = []
        current_sql_query = ""
        for e in reversed(events):
            if e.event_type == "node_end":
                current_sql_history = e.sql_history
                current_sql_query = e.sql_query
                break

        # 按节点分组统计
        node_stats = {}
        for e in events:
            if e.event_type == "node_end":
                if e.node not in node_stats:
                    node_stats[e.node] = {"calls": 0, "total_ms": 0}
                node_stats[e.node]["calls"] += 1
                node_stats[e.node]["total_ms"] += e.elapsed_ms

        return {
            "events": [asdict(e) for e in recent],
            "current_sql_history": current_sql_history,
            "current_sql_query": current_sql_query,
            "node_stats": node_stats,
            "total_events": len(events),
            "session_id": session_id or (events[-1].session_id if events else ""),
            "timestamp": datetime.now().isoformat(),
        }

    def get_events_json(self, session_id: str = "", last_n: int = 50) -> str:
        """获取 JSON 格式的事件列表"""
        return json.dumps(self.get_snapshot(session_id, last_n), ensure_ascii=False, default=str)


def _truncate(s: str, max_len: int = 200) -> str:
    """截断字符串，保留前 max_len 个字符"""
    if not s:
        return ""
    return s[:max_len] + "..." if len(s) > max_len else s


# 全局单例
pipeline_tracker = PipelineTracker()
