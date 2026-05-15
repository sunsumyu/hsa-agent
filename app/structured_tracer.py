"""
app/structured_tracer.py
========================
[企业级可复用模块] 结构化执行追踪器 (M5)

解决问题：
    当前 `execution_trace` 是 List[str]，调试时只能看到文字描述，
    无法精确知道每步的耗时、Token 消耗、成功/失败状态。
    问题：
    1. "Plan Drift"（计划漂移）无法精准定位发生在哪一步
    2. 无法量化每个节点的延迟贡献
    3. LLM 调用成本无法按节点细分

设计原则：
    - 零业务依赖：不 import 任何审计、医保相关模块
    - 兼容现有 List[str] trace：可从旧格式无损升级
    - 轻量序列化：可直接 JSON 序列化注入 Prompt
    - 可独立测试

使用方式：
    from app.structured_tracer import StructuredTracer, TraceEvent

    tracer = StructuredTracer()

    # 记录一次 LLM 调用
    with tracer.span("PLANNER_LLM", node="planner_node") as span:
        response = await llm.ainvoke(prompt)
        span.set_tokens(input=800, output=200)
        span.set_result("GENERATED_SQL")

    # 记录一次 SQL 执行
    with tracer.span("SQL_EXEC", node="sqlexec_node") as span:
        result = execute_sql(sql)
        span.set_result(f"{len(result)} rows")

    # 序列化为字符串注入 Prompt
    trace_str = tracer.format_for_prompt(last_n=5)

    # 序列化为 JSON 保存
    trace_json = tracer.to_dict()

    # 从旧版 List[str] 升级
    tracer = StructuredTracer.from_legacy(state["execution_trace"])
"""

from __future__ import annotations

import time
import json
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Generator
from datetime import datetime


@dataclass
class TraceEvent:
    """单次执行事件的结构化记录"""
    event_id: str                  # 事件标签（如 "PLANNER_LLM"）
    node: str                      # 所在 Agent 节点（如 "planner_node"）
    status: str                    # "SUCCESS" | "FAILURE" | "SKIP"
    result_summary: str            # 简短的结果描述
    started_at: float              # Unix timestamp
    elapsed_ms: int                # 耗时（毫秒）
    input_tokens: int = 0          # 输入 Token 数（估算）
    output_tokens: int = 0         # 输出 Token 数（估算）
    error_msg: str = ""            # 错误信息（失败时）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加信息

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_log_line(self) -> str:
        """格式化为单行日志字符串（兼容旧版 List[str] 格式）"""
        ts = datetime.fromtimestamp(self.started_at).strftime("%H:%M:%S")
        status_icon = {"SUCCESS": "✅", "FAILURE": "❌", "SKIP": "⏭️"}.get(self.status, "•")
        token_info = f" | {self.total_tokens}tok" if self.total_tokens > 0 else ""
        return (
            f"[{ts}] {status_icon} [{self.node}/{self.event_id}] "
            f"{self.result_summary} (+{self.elapsed_ms}ms{token_info})"
        )

    def to_prompt_line(self) -> str:
        """格式化为注入 Prompt 的简洁行（不含时间戳，减少 Token）"""
        status_icon = {"SUCCESS": "✅", "FAILURE": "❌", "SKIP": "⏭️"}.get(self.status, "•")
        return f"{status_icon} {self.event_id}: {self.result_summary}"


class _SpanContext:
    """用于 with 语句的 Span 上下文管理器"""

    def __init__(self, tracer: "StructuredTracer", event_id: str, node: str):
        self._tracer = tracer
        self._event_id = event_id
        self._node = node
        self._start = time.time()
        self._status = "SUCCESS"
        self._result = ""
        self._error = ""
        self._input_tokens = 0
        self._output_tokens = 0
        self._metadata: Dict[str, Any] = {}

    def set_result(self, summary: str):
        """设置结果描述"""
        self._result = str(summary)[:200]

    def set_tokens(self, input: int = 0, output: int = 0):
        """设置 Token 消耗（可以是估算值）"""
        self._input_tokens = input
        self._output_tokens = output

    def set_metadata(self, **kwargs):
        """设置附加元数据"""
        self._metadata.update(kwargs)

    def fail(self, error_msg: str):
        """标记为失败状态"""
        self._status = "FAILURE"
        self._error = str(error_msg)[:300]

    def skip(self, reason: str = ""):
        """标记为跳过状态"""
        self._status = "SKIP"
        self._result = reason or "已跳过"

    def _commit(self):
        elapsed = int((time.time() - self._start) * 1000)
        event = TraceEvent(
            event_id=self._event_id,
            node=self._node,
            status=self._status,
            result_summary=self._result or ("成功" if self._status == "SUCCESS" else self._error[:80]),
            started_at=self._start,
            elapsed_ms=elapsed,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            error_msg=self._error,
            metadata=self._metadata,
        )
        self._tracer._events.append(event)
        # [V171.0] 实时影子推送：如果设置了回调，立即触发
        if self._tracer.on_event_cb:
            try:
                # 支持异步或同步回调
                self._tracer.on_event_cb(event)
            except Exception:
                pass # 追踪失败不应阻塞业务主流程


class StructuredTracer:
    """
    结构化执行追踪器。

    每个 Agent 节点可以用 with tracer.span(...) 记录执行事件，
    支持耗时、Token 消耗、成功/失败状态的精确追踪。
    """

    def __init__(self, session_id: str = "", on_event_cb: Optional[Any] = None):
        self._events: List[TraceEvent] = []
        self.session_id = session_id
        self.on_event_cb = on_event_cb # [V171.0] 影子链路回调接口

    # ──────────────────────────────────────────────────────
    # 核心接口
    # ──────────────────────────────────────────────────────

    @contextmanager
    def span(self, event_id: str, node: str = "") -> Generator[_SpanContext, None, None]:
        """
        上下文管理器：记录一个执行事件的开始和结束。

        Usage:
            with tracer.span("LLM_CALL", node="planner_node") as span:
                response = await llm.ainvoke(...)
                span.set_tokens(input=500, output=200)
                span.set_result("生成了3个审计任务")
        """
        ctx = _SpanContext(self, event_id, node)
        try:
            yield ctx
        except Exception as e:
            ctx.fail(str(e))
            raise
        finally:
            ctx._commit()

    def add_event(
        self,
        event_id: str,
        node: str,
        result: str,
        status: str = "SUCCESS",
        elapsed_ms: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        """直接添加一个事件（不使用 with 语句时的备选）"""
        self._events.append(TraceEvent(
            event_id=event_id,
            node=node,
            status=status,
            result_summary=result[:200],
            started_at=time.time() - elapsed_ms / 1000,
            elapsed_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ))

    def append_legacy(self, text: str):
        """
        兼容旧版 List[str] trace：将文本行转换为 TraceEvent。
        适合在升级迁移期间使用。
        """
        self._events.append(TraceEvent(
            event_id="LEGACY",
            node="unknown",
            status="SUCCESS",
            result_summary=text[:200],
            started_at=time.time(),
            elapsed_ms=0,
        ))

    # ──────────────────────────────────────────────────────
    # 输出接口
    # ──────────────────────────────────────────────────────

    def format_for_prompt(self, last_n: int = 8) -> str:
        """
        生成用于注入 Prompt 的简洁追踪文本。

        Args:
            last_n: 只展示最近 N 个事件，避免占用过多上下文

        Returns:
            多行字符串，每行一个事件
        """
        events = self._events[-last_n:]
        if not events:
            return "（暂无执行记录）"
        return "\n".join(e.to_prompt_line() for e in events)

    def to_legacy_list(self) -> List[str]:
        """
        转换为旧版 List[str] 格式（与 AuditState.execution_trace 兼容）。
        """
        return [e.to_log_line() for e in self._events]

    def to_dict(self) -> Dict:
        """序列化为 JSON 可持久化格式"""
        return {
            "session_id": self.session_id,
            "total_events": len(self._events),
            "total_elapsed_ms": sum(e.elapsed_ms for e in self._events),
            "total_tokens": sum(e.total_tokens for e in self._events),
            "events": [asdict(e) for e in self._events],
        }

    def get_summary(self) -> str:
        """生成一行摘要（适合 logger 输出）"""
        success = sum(1 for e in self._events if e.status == "SUCCESS")
        fail = sum(1 for e in self._events if e.status == "FAILURE")
        total_ms = sum(e.elapsed_ms for e in self._events)
        total_tok = sum(e.total_tokens for e in self._events)
        return (
            f"事件总数={len(self._events)} ✅{success} ❌{fail} | "
            f"总耗时={total_ms}ms | 总Token={total_tok}"
        )

    @property
    def has_failure(self) -> bool:
        return any(e.status == "FAILURE" for e in self._events)

    @property
    def events(self) -> List[TraceEvent]:
        return list(self._events)

    # ──────────────────────────────────────────────────────
    # 工厂方法
    # ──────────────────────────────────────────────────────

    @classmethod
    def from_legacy(cls, legacy_trace: List[str], session_id: str = "") -> "StructuredTracer":
        """
        从旧版 List[str] trace 无损升级到 StructuredTracer。

        Args:
            legacy_trace: AuditState 中旧版的 execution_trace 字段

        Returns:
            填充了等效事件的 StructuredTracer 实例
        """
        tracer = cls(session_id=session_id)
        for item in (legacy_trace or []):
            tracer.append_legacy(str(item))
        return tracer

    @classmethod
    def merge(cls, *tracers: "StructuredTracer") -> "StructuredTracer":
        """合并多个 tracer（适合并行节点汇总）"""
        merged = cls()
        for t in tracers:
            merged._events.extend(t._events)
        merged._events.sort(key=lambda e: e.started_at)
        return merged
