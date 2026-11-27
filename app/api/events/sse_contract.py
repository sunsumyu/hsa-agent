"""
app.api.events.sse_contract — 强类型流式通信协议契约 (Matt Pocock Deep Module)
=======================================================================
定义严格的 Server-Sent Events (SSE) 协议帧结构，取代散落的 [[[...]]] 弱类型字符串。

契约特性:
1. 强枚举事件类型: 区分状态(status)、推演(thought)、正文(message)、资源(resource)等
2. 双轨格式化能力:
   - to_sse_packet(): 输出标准 W3C SSE 格式 (event: ...\\ndata: ...\\n\\n)
   - to_legacy_packet(): 输出历史兼容的 [[[...]]] 格式，保证旧版 Rust/WASM 前端 0 破坏
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class SSEEventType(str, Enum):
    """标准的 SSE 协议事件类型枚举"""
    ENGINE = "engine"          # 物理模型与执行引擎元数据
    VERSION = "version"        # 协议与引擎版本号
    STATUS = "status"          # UI 顶部指示器/阶段状态信令
    THOUGHT = "thought"        # 内部专家推演/思考日志 (前端折叠)
    MESSAGE = "message"        # 正文交付内容 (前端气泡渲染)
    RESOURCE = "resource"      # Token 消耗与计费遥测
    ACTION = "action"          # 3D 联动动作 (如 MOVE, SCHEMA, SQL)
    SESSION_TITLE = "session_title"  # 会话标题即时/精炼同步事件
    ERROR = "error"            # 运行时异常与熔断警告
    DONE = "done"              # 推演流式正常结束信令


class SSEEvent(BaseModel):
    """标准的强类型 SSE 事件帧 (SSOT)"""
    event: SSEEventType = Field(description="事件类型")
    data: Union[str, Dict[str, Any]] = Field(description="事件负载数据")
    id: Optional[str] = Field(default=None, description="事件唯一递增序号 (可选)")
    retry: Optional[int] = Field(default=None, description="客户端重连间隔毫秒 (可选)")

    def to_sse_packet(self) -> str:
        """格式化为标准 W3C Server-Sent Events 数据包"""
        lines = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event.value}")
        
        # 序列化 data 字段
        if isinstance(self.data, (dict, list)):
            payload = json.dumps(self.data, ensure_ascii=False)
        else:
            payload = str(self.data)
        
        for subline in payload.splitlines():
            lines.append(f"data: {subline}")
        
        return "\n".join(lines) + "\n\n"

    def to_legacy_packet(self) -> str:
        """向后兼容模式: 格式化为历史的 [[[...]]] 带内暗号或纯文本"""
        if self.event == SSEEventType.ENGINE:
            return f"[[[ENGINE:{self.data}]]]"
        elif self.event == SSEEventType.VERSION:
            return f"[[[VERSION:{self.data}]]]"
        elif self.event == SSEEventType.STATUS:
            msg = self.data.get("message", self.data) if isinstance(self.data, dict) else self.data
            return f"[[[STATUS: {msg}]]]\n\n"
        elif self.event == SSEEventType.RESOURCE:
            payload = json.dumps(self.data, ensure_ascii=False) if isinstance(self.data, dict) else self.data
            return f"\n\n[[[RESOURCE: {payload}]]]\n\n"
        elif self.event == SSEEventType.THOUGHT:
            # 格式化推演日志
            return str(self.data)
        elif self.event == SSEEventType.MESSAGE:
            return str(self.data)
        elif self.event == SSEEventType.ACTION:
            action_type = self.data.get("type", "ACTION") if isinstance(self.data, dict) else "ACTION"
            val = self.data.get("value", "") if isinstance(self.data, dict) else self.data
            return f"[[[{action_type}:{val}]]]"
        elif self.event == SSEEventType.SESSION_TITLE:
            title = self.data.get("title", self.data) if isinstance(self.data, dict) else self.data
            return f"[[[TITLE:{title}]]]"
        elif self.event == SSEEventType.ERROR:
            msg = self.data.get("message", self.data) if isinstance(self.data, dict) else self.data
            return f"\n\n⚠️ 异常: {msg}\n\n"
        elif self.event == SSEEventType.DONE:
            return ""
        return str(self.data)
