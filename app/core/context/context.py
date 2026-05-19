"""
app/core/context.py
===================
[V160.0] 物理上下文管理器 (Execution Context)

利用 ContextVar 实现协程安全的上下文存储，用于多租户隔离与全链路追踪。
"""

from contextvars import ContextVar
from typing import Optional

# 租户 ID 上下文
tenant_context: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

# 追踪 ID 上下文
trace_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
