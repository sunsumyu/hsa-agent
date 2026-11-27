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
from typing import Any, List, Sequence, Tuple
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from app.core.memory.message_sanitizer import ensure_tool_pairing


def _msg_role(msg: Any) -> str:
    m_type = getattr(msg, "type", msg.__class__.__name__).lower()
    if m_type in ("human", "user") or (isinstance(msg, tuple) and msg[0] in ("human", "user")):
        return "user"
    return "assistant" if m_type in ("ai", "assistant") else "other"


def _split_system_and_dialogue(paired_messages: Sequence[Any]) -> Tuple[List[str], List[Any], bool]:
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
    return system_contents, non_system_messages, has_cache_flag


def _merge_consecutive_roles(non_system_messages: Sequence[Any]) -> List[Any]:
    merged_dialogue: List[Any] = []
    for m in non_system_messages:
        m_role = _msg_role(m)
        if merged_dialogue and m_role in ("user", "assistant"):
            prev_m = merged_dialogue[-1]
            if m_role == _msg_role(prev_m) and not getattr(prev_m, "tool_calls", None) and not getattr(m, "tool_calls", None):
                prev_c = str(prev_m[1] if isinstance(prev_m, tuple) else getattr(prev_m, "content", "") or "")
                curr_c = str(m[1] if isinstance(m, tuple) else getattr(m, "content", "") or "")
                merged_c = f"{prev_c}\n\n{curr_c}".strip()
                merged_dialogue[-1] = HumanMessage(content=merged_c) if m_role == "user" else AIMessage(content=merged_c)
                continue
        merged_dialogue.append(m)
    return merged_dialogue


def _normalize_to_base_messages(non_system_messages: Sequence[Any]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
    for m in non_system_messages:
        if isinstance(m, tuple) and len(m) >= 2:
            msg_cls = AIMessage if str(m[0]).lower() in ("ai", "assistant") else HumanMessage
            result.append(msg_cls(content=str(m[1])))
        elif isinstance(m, BaseMessage):
            result.append(m)
    return result


def sanitize_dialogue_protocol(messages: Sequence[Any]) -> List[BaseMessage]:
    """对传入 LLM 的消息历史进行严格的协议防御与标准化。"""
    if not messages:
        return [HumanMessage(content="请根据系统提示与当前上下文执行审计分析并给出输出。")]

    paired = ensure_tool_pairing(list(messages))
    system_contents, non_system_messages, has_cache_flag = _split_system_and_dialogue(paired)
    merged_dialogue = _merge_consecutive_roles(non_system_messages)

    final_messages: List[BaseMessage] = []
    if system_contents:
        merged_sys = "\n\n---\n\n".join(system_contents)
        add_kwargs = {"cache_control": {"type": "ephemeral"}} if (has_cache_flag or len(merged_sys) >= 1024) else {}
        final_messages.append(SystemMessage(content=merged_sys, additional_kwargs=add_kwargs))

    final_messages.extend(_normalize_to_base_messages(merged_dialogue))
    if not any(isinstance(m, HumanMessage) or getattr(m, "type", "") in ("human", "user") for m in final_messages):
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
