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
    from app.core.memory.message_sanitizer import sanitize_for_thinking_mode, trim_and_sanitize

    # 在传递消息给 LLM 前净化
    safe_msgs = sanitize_for_thinking_mode(state["messages"])
    prompt = template.format_messages(messages=safe_msgs, ...)

    # 合并+净化（替代 LangGraph 的 _trim_messages）
    merged = trim_and_sanitize(left_msgs, right_msgs, max_total=15, keep_tail=7)
"""

from __future__ import annotations

import re as _re
from typing import List, Any, Optional, Dict

# [Matt Pocock Deep Module] Tool call protocol pairing, compactor, and pruning
from app.core.memory.tool_protocol_guard import (
    compress_tool_content,
    ensure_tool_pairing,
    prune_past_turn_tools,
)


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


# ── 噪音特征 ──────────────────────────────────────────────────
_NOISE_RE = _re.compile(
    r"^[\s\d\.\,\;\:\'\"\\n\\t\#\*\-\+\=\!\?]*$"  # 纯标点/数字/空白
)

_NOISE_KEYWORDS = frozenset({
    "ping", "pong", "ok", "1", "test", "hello", "hi",
    "...", "null", "none", "undefined", ""
})


def remove_noise(messages: List[Any]) -> List[Any]:
    """
    [V90.5] 无条件去噪：删除所有无意义消息。始终执行，不受阈值控制。

    删除条件（满足任一即删）：
    - 内容为空 / 纯空白
    - 内容为纯数字、纯标点
    - 内容是已知探活词（ping, test, ok 等）
    - 内容长度 < 3 且不是 ToolMessage（ToolMessage 可能有短状态码）
    - AIMessage 内容为空且无 tool_calls
    """
    clean = []
    for m in messages:
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        content = str(getattr(m, "content", "") or "").strip()

        # 空内容 AI 且无 tool_calls → 丢弃；有 tool_calls ── 保留 (防止工具调用声明丢失)
        if msg_type in ("ai", "assistant", "aimessagechunk"):
            has_tc = bool(getattr(m, "tool_calls", None)) or bool((getattr(m, "additional_kwargs", {}) or {}).get("tool_calls", []))
            if not content:
                if has_tc:
                    clean.append(m)
                continue

        # ToolMessage 不按内容过滤（即使短内容也有协议意义）
        if msg_type == "tool":
            clean.append(m)
            continue

        # 空内容
        if not content:
            continue

        # 已知噪音词
        if content.lower() in _NOISE_KEYWORDS:
            continue

        # 纯数字/标点/空白
        if _NOISE_RE.match(content):
            continue

        # 内容太短（< 3 字符）且非 system
        if len(content) < 3 and msg_type != "system":
            continue

        clean.append(m)
    return clean


def dedup_messages(messages: List[Any]) -> List[Any]:
    """
    [V90.5] 无条件去重：删除所有重复消息。始终执行，不受阈值控制。

    去重规则：
    - HumanMessage: 按 content 前 200 字符去重，只保留首条
    - ToolMessage: 按 tool_call_id 去重，只保留最后一条
    - AIMessage: 按 content 前 300 字符去重（含 tool_calls 的按 tool_call name 列表去重）
    - SystemMessage: 按 content 前 200 字符去重，只保留首条
    """
    # Pass 1: 标记 ToolMessage 最后出现位置
    last_tool_idx = {}
    for i, m in enumerate(messages):
        tid = getattr(m, "tool_call_id", None)
        if tid:
            last_tool_idx[tid] = i

    seen_human = set()
    seen_system = set()
    seen_ai = set()
    result = []

    for i, m in enumerate(messages):
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        content = str(getattr(m, "content", "") or "")

        if msg_type == "human":
            key = content[:200].strip()
            if key in seen_human:
                continue
            seen_human.add(key)

        elif msg_type == "system":
            key = content[:200].strip()
            if key in seen_system:
                continue
            seen_system.add(key)

        elif msg_type == "ai":
            tc = getattr(m, "tool_calls", None) or []
            if tc:
                # [Fix] AIMessage with tool_calls represents execution steps and must not be deduplicated,
                # otherwise subsequent ToolMessages will be orphaned and discarded, causing infinite loop.
                pass
            else:
                key = content[:300].strip()
                if key in seen_ai:
                    continue
                seen_ai.add(key)

        elif msg_type == "tool":
            tid = getattr(m, "tool_call_id", None)
            if tid and tid in last_tool_idx and i != last_tool_idx[tid]:
                continue

        result.append(m)
    return result



def trim_overflow(messages: List[Any], max_total: int = 12, keep_head: int = 2, keep_tail: int = 6) -> List[Any]:
    """
    [V90.5] 超限裁剪：仅在总量超标时执行，保留头尾关键消息。
    与去重/去噪无关，独立职责。
    """
    if len(messages) <= max_total:
        return messages
    return messages[:keep_head] + messages[-keep_tail:]



def trim_and_sanitize(
    left: List[Any],
    right: List[Any],
    max_total: int = 12,
    keep_head: int = 2,
    keep_tail: int = 6,
    ai_label_prefix: str = "[Agent历史分析结果]",
    sanitize_thinking: bool = False,
) -> List[Any]:
    """
    [V90.6] 企业级消息合并 reducer。

    独立治理阶段：
        1. 格式统一 (Role Map)           — tuple 转 Message 对象
        2. 无条件去噪 (remove_noise)      — 删除空白与探活噪音
        3. 无条件去重 (dedup_messages)     — 删除完全重复消息
        4. 历史修剪 (prune_past_turn_tools) — 清理已结算轮次的中间 Tool 碎片
        5. 压缩 (compress_tool_content)  — 截断当前活跃轮次过长的 ToolMessage
        6. 净化 (sanitize_for_thinking_mode) — 仅在显式声明时开启 Thinking Mode 兼容
        7. 裁剪 (trim_overflow)          — 仅在超限时裁剪非关键中间消息
        8. 配对校验 (ensure_tool_pairing) — 确保 ToolMessage 有对应的 AI tool_calls
        9. 内容脱敏 (sanitize_audit_content) — 脱敏 PII 并移除多余 SQL trace
    """
    combined = list(left or []) + list(right or [])

    # [V90.6] 物理转换：tuple ("user"/"human"/"ai"/"system", content) → Message 对象
    # LangGraph 入口可能传 tuple，sanitizer 的所有子函数依赖 .type/.content 属性
    from langchain_core.messages import HumanMessage as _HM, AIMessage as _AM, SystemMessage as _SM
    _ROLE_MAP = {"user": _HM, "human": _HM, "ai": _AM, "assistant": _AM, "system": _SM}
    _converted = []
    for m in combined:
        if isinstance(m, tuple) and len(m) >= 2:
            role_str = str(m[0]).lower()
            msg_cls = _ROLE_MAP.get(role_str, _HM)
            _converted.append(msg_cls(content=str(m[1])))
        else:
            _converted.append(m)
    combined = _converted

    combined = remove_noise(combined)
    combined = dedup_messages(combined)
    # [SPEC-227 状态防腐] 历史轮次内部工具修剪，防止跨轮次工具残留与上下文腐化
    combined = prune_past_turn_tools(combined)
    # [V228.0 瘦身] 压缩过长 ToolMessage，保留 tool_call_id 与原始数据指针，防止历史 ToolMessage 撑爆 Token
    combined = compress_tool_content(combined)
    if sanitize_thinking:
        combined = sanitize_for_thinking_mode(combined, ai_label_prefix=ai_label_prefix)
    combined = trim_overflow(combined, max_total=max_total, keep_head=keep_head, keep_tail=keep_tail)
    combined = ensure_tool_pairing(combined)
    # [V166.0] 阶段 7：内容脱敏与 SQL 净化
    combined = sanitize_audit_content(combined)

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


# [Matt Pocock Deep Module] 委托至专职的医保隐私合规与 PII 脱敏深模块
from app.core.security.data_masker import (
    apply_pii_masking as _apply_pii_masking,
    sanitize_audit_content,
    mask_audit_data,
)
