"""
app/message_sanitizer.py
========================
[企业级可复用模块] LLM 消息历史兼容性净化器

解决问题：
    Doubao/Volcengine 等 Thinking Mode 模型对对话历史有严格约束：
    assistant 消息必须携带非空的 reasoning_content，否则触发 400 InvalidParameter。
    LangChain 不会在 AIMessage 中可靠地存储 reasoning_content，
    导致历史消息回放时触发 API 拒绝。

设计原则：
    - 零业务依赖：不 import 任何审计、医保相关模块
    - 无状态：函数式设计，无副作用
    - 可独立测试：不依赖完整 Agent 图
    - 兼容所有 LangChain 项目

使用方式：
    from app.message_sanitizer import sanitize_for_thinking_mode, trim_and_sanitize

    # 在传递消息给 LLM 前净化
    safe_msgs = sanitize_for_thinking_mode(state["messages"])
    prompt = template.format_messages(messages=safe_msgs, ...)

    # 合并+净化（替代 LangGraph 的 _trim_messages）
    merged = trim_and_sanitize(left_msgs, right_msgs, max_total=15, keep_tail=7)
"""

from __future__ import annotations

from typing import List, Any, Optional


def sanitize_for_thinking_mode(
    messages: List[Any],
    ai_label_prefix: str = "[Agent历史分析结果]",
) -> List[Any]:
    """
    净化消息列表，使其兼容 Thinking Mode LLM（如 Doubao/Volcengine 思考模型）。

    策略：
        - SystemMessage / HumanMessage / ToolMessage：原样保留
        - AIMessage (含 tool_calls)：原样保留（工具调用协议不能破坏）
        - AIMessage (不含 tool_calls)：降级为带标签的 HumanMessage
          - 原因：LangChain 序列化时会给所有 assistant 消息加 reasoning_content:''，
                  而 Thinking Mode 模型要求此字段非空，否则触发 400
          - 处理：将内容保留为 `[AI Label] {content}` 格式的 HumanMessage
        - AIMessage (内容为空 + 无 tool_calls)：直接丢弃

    Args:
        messages: LangChain 消息列表（可包含任意 Message 类型）
        ai_label_prefix: 降级 AIMessage 时的内容前缀标签

    Returns:
        净化后的消息列表，可安全传递给任何 Thinking Mode LLM
    """
    try:
        from langchain_core.messages import HumanMessage as _HumanMessage
    except ImportError:
        # 如果没有 LangChain，直接原样返回（向前兼容）
        return list(messages)

    safe_messages = []
    for msg in messages:
        cls_name = msg.__class__.__name__

        is_ai = (
            cls_name in ("AIMessage", "AIMessageChunk")
            or getattr(msg, "type", "") == "ai"
            or getattr(msg, "role", "") == "assistant"
        )

        if is_ai:
            # 检查是否包含 tool_calls（有 tool_calls 的 AIMessage 必须保留原格式）
            tool_calls = getattr(msg, "tool_calls", None) or []
            tc_in_kwargs = (
                (getattr(msg, "additional_kwargs", {}) or {}).get("tool_calls", []) or []
            )
            has_tool_calls = bool(tool_calls) or bool(tc_in_kwargs)

            if not has_tool_calls:
                # 纯分析型 AIMessage → 降级为 HumanMessage
                content = getattr(msg, "content", "") or ""
                content_str = str(content).strip()
                if content_str:
                    safe_messages.append(
                        _HumanMessage(content=f"{ai_label_prefix} {content_str}")
                    )
                # 空内容 AIMessage 直接丢弃，无需保留
                continue

        safe_messages.append(msg)

    return safe_messages


def trim_and_sanitize(
    left: List[Any],
    right: List[Any],
    max_total: int = 15,
    keep_head: int = 3,
    keep_tail: int = 7,
    ai_label_prefix: str = "[Agent历史分析结果]",
) -> List[Any]:
    """
    合并两段消息历史，裁剪过长部分，并对结果进行 Thinking Mode 净化。

    适合作为 LangGraph Annotated 字段的 reducer 函数使用：
        messages: Annotated[Sequence[BaseMessage], trim_and_sanitize]

    Args:
        left: 旧消息列表
        right: 新消息列表
        max_total: 超过此数量时触发裁剪
        keep_head: 裁剪时保留头部消息数（含系统消息和首条用户消息）
        keep_tail: 裁剪时保留尾部消息数（最新进展）
        ai_label_prefix: 降级 AIMessage 时的标签前缀

    Returns:
        净化且裁剪后的消息列表
    """
    combined = list(left or []) + list(right or [])
    # 先净化，再裁剪（顺序很重要：净化可能减少总数）
    combined = sanitize_for_thinking_mode(combined, ai_label_prefix=ai_label_prefix)

    if len(combined) > max_total:
        head = combined[:keep_head]
        tail = combined[-keep_tail:]
        combined = head + tail

    return combined


def count_message_tokens_estimate(messages: List[Any]) -> int:
    """
    快速估算消息列表的 Token 总量（粗粒度，无需加载 tiktoken）。

    适用于决策是否需要裁剪，不适用于精确计费。

    Returns:
        估算的 Token 数量
    """
    total = 0
    for msg in messages:
        content = getattr(msg, "content", "") or ""
        text = str(content)
        # 中文字符约 1.5 token，其他字符约 0.4 token
        zh_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        en_count = len(text) - zh_count
        total += int(zh_count * 1.5 + en_count * 0.4)
    return total
