"""
app.api.chat_stream — [重构 V90.0] chat() God Function 的拆解模块
================================================================
原 @app.main.chat() 374 行合并了 5 类不相关关注点:
  1. HTTP 请求解析
  2. LangGraph 事件流遍历
  3. 前端协议标签 ([[[ENGINE:...]]], [[[MOVE:...]]] 等) 的生成
  4. 节点/工具/模型流事件分发
  5. 异常分类与自愈

本模块拆出 #1、#3、#5 的纯函数/生成器。chat() 保留 #2、#4 的主循环编排。
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from loguru import logger


# ──────────────────────────────────────────────────────────────
# #1 请求解析
# ──────────────────────────────────────────────────────────────

async def parse_chat_request(request) -> Tuple[str, Optional[str], str]:
    """
    从 FastAPI Request 中提取 (message, model_id, session_id)。
    
    兼容多种 payload:
      - JSON: {"input": "...", "message": "...", "query": "...", "modelId": "..."}
      - 原始文本: "..."
    """
    body = await request.body()
    data = None
    try:
        data = json.loads(body.decode("utf-8"))
        if isinstance(data, dict):
            # [Clean Seam] 宽容性接缝：兼容 input / message / query / content / prompt / text
            message = ""
            for key in ["input", "message", "query", "content", "prompt", "text", "user_input"]:
                if key in data and data[key] is not None and str(data[key]).strip():
                    message = str(data[key]).strip()
                    break
            if not message:
                message = str(data)
            model_id = data.get("modelId") or data.get("model_id")
        else:
            message = str(data).strip()
            model_id = None
    except Exception:
        message = body.decode("utf-8").strip()
        model_id = None

    session_id = request.headers.get("X-Session-Id", "default-python-session")
    if isinstance(data, dict) and data.get("session_id"):
        session_id = str(data["session_id"])
    return message, model_id, session_id


from app.api.stream_protocol_renderer import (
    stream_protocol_renderer,
    _NODE_DISPLAY_NAMES,
    _NODE_WORLDS,
)
from app.api.stream_circuit_breaker import stream_circuit_breaker


# ──────────────────────────────────────────────────────────────
# #3 前端协议标签生成 (委托给 StreamProtocolRenderer 深模块)
# ──────────────────────────────────────────────────────────────

def emit_node_status(check_name: str, name: str) -> list[str]:
    """当 LangGraph 切换节点时生成一组前端协议标签。"""
    return stream_protocol_renderer.render_node_status(check_name, name)


def emit_tool_start_events(name: str, inputs: Dict[str, Any]) -> list[str]:
    """工具启动时生成 3D UI 联动包 (MOVE/LOGIC/SQL/BOOKSHELF)。"""
    return stream_protocol_renderer.render_tool_start_events(name, inputs)


# ──────────────────────────────────────────────────────────────
# #5 错误分类与自愈文案 (委托给 StreamCircuitBreaker 深模块)
# ──────────────────────────────────────────────────────────────

def classify_and_render_error(
    err_msg: str,
    resolved_id: Optional[str],
    usage_tracker,
    model_manager,
    background_tasks,
) -> list[str]:
    """根据错误类型返回 UI 需要的自愈文案列表。"""
    return stream_circuit_breaker.classify_and_render(
        err_msg=err_msg,
        resolved_id=resolved_id,
        usage_tracker=usage_tracker,
        model_manager=model_manager,
        background_tasks=background_tasks,
    )


# ──────────────────────────────────────────────────────────────
# #6 流式事件规范化与辅助渲染函数 (委托给 StreamProtocolRenderer 深模块)
# ──────────────────────────────────────────────────────────────

def extract_stream_chunk_text(content: Any) -> str:
    """规范化提取 LLM 流式输出 Chunk 中的文本内容。"""
    return stream_protocol_renderer.extract_chunk_text(content)


def format_resource_telemetry(usage: Optional[Dict[str, Any]], node_or_role: str) -> Optional[str]:
    """计算算力 Token 消耗与成本，生成前端遥测标签 [[[RESOURCE:...]]]。"""
    return stream_protocol_renderer.render_resource_telemetry(usage, node_or_role)


def format_tool_trace_packet(name: str, output: Any, max_len: int = 1000) -> Optional[str]:
    """针对关键审计取证工具生成 UI 追踪 Markdown 容器。"""
    return stream_protocol_renderer.render_tool_trace(name, output, max_len)


def render_human_review_card(snapshot_values: Optional[Dict[str, Any]]) -> str:
    """当 LangGraph 图在中断点挂起（如人工介入审核）时，渲染指引卡片。"""
    return stream_protocol_renderer.render_human_review_card(snapshot_values)



def render_meta_envelope(run_id: str, session_id: str) -> str:
    """渲染会话元数据帧，向前端透传 Run ID 与 Session ID。"""
    return stream_protocol_renderer.render_meta_envelope(run_id, session_id)
