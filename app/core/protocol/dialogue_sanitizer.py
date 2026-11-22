"""
app/core/protocol/dialogue_sanitizer.py
=======================================
[Deep Module] LLM 对话协议归一化与防御模块。

设计哲学 (Matt Pocock Deep Module Principles):
    - 狭窄接口 (Narrow Interface): 仅公开 `sanitize_dialogue_protocol` 和 `unpack_response_content`。
    - 深层实现 (Deep Implementation): 内聚处理 Anthropic/OpenAI/PPIO 多厂商协议异构性、
      分散 SystemMessage 归一化与 Ephemeral Cache 标记、连续同角色消息交替折叠、
      工具调用配对完整性校验、以及 Claude/Thinking 多分块内容解包。
    - 纯函数与无副作用: 输入消息序列，输出防御完成的消息序列，消除外部调用方的变量漫步与状态污染。
"""

from __future__ import annotations
from typing import List, Any, Sequence
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.core.memory.message_sanitizer import ensure_tool_pairing


def sanitize_dialogue_protocol(messages: Sequence[Any]) -> List[BaseMessage]:
    """
    对传入 LLM 的消息历史进行严格的协议防御与标准化。
    
    保障：
    1. 工具调用配对 100% 完整（消除孤儿 ToolMessage 导致的 400 Bad Request）。
    2. 合并所有分散的 SystemMessage 为单一头部系统消息，防止多 System 导致的静默空响应。
    3. 超过 1024 字符或原本具备 cache 标记的 SystemMessage 自动注入 ephemeral 缓存控制。
    4. 严格满足 user / assistant 角色交替（折叠连续同角色纯文本消息）。
    5. 当全为系统指令或缺失用户消息时，自动保底追加 HumanMessage，防止模型接口拒绝。
    """
    if not messages:
        return [HumanMessage(content="请根据系统提示与当前上下文执行审计分析并给出输出。")]

    # 1. 确保工具调用配对完整
    paired_messages = ensure_tool_pairing(list(messages))

    # 2. 分离并提取 SystemMessage 与 非系统消息
    system_contents: List[str] = []
    non_system_messages: List[Any] = []
    has_cache_flag = False

    for m in paired_messages:
        is_sys = isinstance(m, SystemMessage) or getattr(m, "type", "") == "system" or (isinstance(m, tuple) and m[0] == "system")
        if is_sys:
            c = m[1] if isinstance(m, tuple) else getattr(m, "content", "")
            if c:
                system_contents.append(str(c).strip())
            if not isinstance(m, tuple) and getattr(m, "additional_kwargs", {}).get("cache_control"):
                has_cache_flag = True
        else:
            non_system_messages.append(m)

    # 3. 合并连续同角色对话消息，确保满足 user / assistant 交替
    merged_dialogue: List[Any] = []
    for m in non_system_messages:
        m_type = getattr(m, "type", m.__class__.__name__).lower()
        m_role = "user" if m_type in ("human", "user") or (isinstance(m, tuple) and m[0] in ("human", "user")) else (
            "assistant" if m_type in ("ai", "assistant") else "other"
        )
        
        if merged_dialogue and m_role in ("user", "assistant"):
            prev_m = merged_dialogue[-1]
            prev_type = getattr(prev_m, "type", prev_m.__class__.__name__).lower()
            prev_role = "user" if prev_type in ("human", "user") or (isinstance(prev_m, tuple) and prev_m[0] in ("human", "user")) else (
                "assistant" if prev_type in ("ai", "assistant") else "other"
            )
            
            # 若前后角色相同且均不含 tool_calls，则合并其纯文本
            if m_role == prev_role and not getattr(prev_m, "tool_calls", None) and not getattr(m, "tool_calls", None):
                prev_c = str(prev_m[1] if isinstance(prev_m, tuple) else getattr(prev_m, "content", "") or "")
                curr_c = str(m[1] if isinstance(m, tuple) else getattr(m, "content", "") or "")
                new_c = f"{prev_c}\n\n{curr_c}".strip()
                if m_role == "user":
                    merged_dialogue[-1] = HumanMessage(content=new_c)
                else:
                    merged_dialogue[-1] = AIMessage(content=new_c)
                continue
        merged_dialogue.append(m)

    non_system_messages = merged_dialogue

    # 4. 重组头部单一 SystemMessage
    final_messages: List[BaseMessage] = []
    if system_contents:
        merged_sys_content = "\n\n---\n\n".join(system_contents)
        if len(merged_sys_content) >= 1024:
            has_cache_flag = True
        
        add_kwargs = {"cache_control": {"type": "ephemeral"}} if has_cache_flag else {}
        final_messages.append(SystemMessage(content=merged_sys_content, additional_kwargs=add_kwargs))
    
    # 将可能为 tuple 的消息归一化为 BaseMessage
    for m in non_system_messages:
        if isinstance(m, tuple) and len(m) >= 2:
            role_str = str(m[0]).lower()
            if role_str in ("user", "human"):
                final_messages.append(HumanMessage(content=str(m[1])))
            elif role_str in ("ai", "assistant"):
                final_messages.append(AIMessage(content=str(m[1])))
            else:
                final_messages.append(HumanMessage(content=str(m[1])))
        elif isinstance(m, BaseMessage):
            final_messages.append(m)

    # 5. 保底检查：若无用户消息，自动追加一条 HumanMessage 防止模型接口报错
    has_user_msg = any(
        isinstance(m, HumanMessage) or getattr(m, "type", "") in ("human", "user")
        for m in final_messages
    )
    if not has_user_msg:
        final_messages.append(HumanMessage(content="请根据系统提示与当前上下文执行审计分析并给出输出。"))

    return final_messages


def unpack_response_content(content: Any, has_tool_calls: bool = False) -> Any:
    """
    归一化 LLM response.content 为标准纯文本字符串。
    
    解决问题：
    Claude/Thinking 等模型流式或特定输出下，response.content 可能为 block 列表：
    - `[{'type': 'text', 'text': '...'}]`
    - `['part1', 'part2']`
    若不解包，下游 JSON 提取、报告渲染或正则匹配会因 AttributeError/TypeError 崩溃。
    """
    if not isinstance(content, list):
        return content

    text_parts: List[str] = []
    for item in content:
        if isinstance(item, str):
            if item:
                text_parts.append(item)
        elif isinstance(item, dict):
            if item.get("type") == "text" and item.get("text"):
                text_parts.append(str(item["text"]))
            elif "text" in item and item["text"]:
                text_parts.append(str(item["text"]))

    if text_parts or not has_tool_calls:
        return "\n".join(text_parts).strip()

    return content
