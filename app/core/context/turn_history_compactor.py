"""
[SPEC-227 / Matt Pocock Deep Module] 会话历史压缩与自适应预算治理深模块 (Turn History Compactor)

核心职责：
1. 估算消息与文本的高精度混合 Token 预算。
2. 对前序已完结轮次的探针调用与冗余巨幅底稿进行高保真瘦身脱水，保留活跃交互。
3. 当整链 Token 超过硬件/模型最大输入预算时，执行分区感知式确定性事实摘要提炼与安全截断，
   杜绝引入二次 LLM 调用的 15s 延迟与幻觉。
"""

from __future__ import annotations
import re
from typing import Any, Callable, List, Optional, Sequence, Tuple
from loguru import logger
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage


def estimate_tokens(text: Any) -> int:
    """中英混合高精度 Token 估算器纯函数"""
    if not text:
        return 0
    if isinstance(text, list):
        text_parts = []
        for item in text:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                text_parts.append(str(item["text"]))
            else:
                text_parts.append(str(item))
        text = " ".join(text_parts)
    elif not isinstance(text, str):
        text = str(text)

    chinese_chars = sum(1 for ch in text if isinstance(ch, str) and "\u4e00" <= ch <= "\u9fff")
    english_words = len([w for w in text.split() if w])
    return int(chinese_chars + english_words * 1.3)


def compact_past_turns(chat_msgs: Sequence[BaseMessage]) -> List[BaseMessage]:
    """
    [SPEC-227 会话级长链上下文治理]
    将前序已完结轮次的中间探针工具调用与冗长渲染底稿脱水压缩，
    仅保留 (HumanMessage -> 紧凑 AIMessage 结论) 的纯净交互骨架；
    当前正在进行的活跃轮次 (最后一个 HumanMessage 之后的所有消息) 保持 100% 原始完整度。
    """
    if not chat_msgs:
        return []

    # 定位当前轮次的起始点 (最后一个 HumanMessage)
    last_human_idx = -1
    for idx in range(len(chat_msgs) - 1, -1, -1):
        if getattr(chat_msgs[idx], "type", "") in ("human", "user"):
            last_human_idx = idx
            break

    if last_human_idx <= 0:
        # 单轮交互或首轮提问，直接原样返回
        return list(chat_msgs)

    past_msgs = chat_msgs[:last_human_idx]
    active_msgs = list(chat_msgs[last_human_idx:])

    compacted_past: List[BaseMessage] = []
    for m in past_msgs:
        m_type = getattr(m, "type", m.__class__.__name__).lower()
        if m_type in ("human", "user"):
            compacted_past.append(m)
        elif m_type in ("ai", "assistant", "aimessage", "aimessagechunk"):
            content = str(getattr(m, "content", "") or "").strip()
            # 过滤前序轮次的纯中间工具调用（如仅有 tool_calls 但无实质结论文本的 AIMessage）
            has_tc = bool(getattr(m, "tool_calls", None))
            if has_tc and len(content) < 40:
                continue

            # 对前序已完结轮次的巨幅底稿文本进行高保真瘦身
            if len(content) > 300:
                summary_match = re.search(
                    r"(?:###?\s*(?:审计结论|核查结论|核心指标|发现总结|结论)[^\n]*\n)(.*?)(?:\n###|\n##|\Z)",
                    content,
                    re.DOTALL,
                )
                if summary_match and len(summary_match.group(1).strip()) > 20:
                    clean_content = summary_match.group(1).strip()[:300]
                else:
                    clean_content = content[:300]
                compacted_past.append(AIMessage(content=f"{clean_content} ...[前序底稿已归档]"))
            elif content:
                compacted_past.append(AIMessage(content=content))
        # 过滤前序轮次的 ToolMessage（中间数据事实已安全固化在 accumulated_findings 与 GSSC 中）

    return compacted_past + active_msgs


def _partition_messages(
    messages: Sequence[BaseMessage],
) -> Tuple[List[BaseMessage], Optional[BaseMessage], List[BaseMessage]]:
    system_msgs: List[BaseMessage] = []
    gssc_msg: Optional[BaseMessage] = None
    chat_msgs: List[BaseMessage] = []
    for m in messages:
        if isinstance(m, SystemMessage) and "【当前审计黄金上下文载荷" in str(getattr(m, "content", "")):
            gssc_msg = m
        elif getattr(m, "type", "") == "system":
            system_msgs.append(m)
        else:
            chat_msgs.append(m)
    return system_msgs, gssc_msg, chat_msgs


def _build_deterministic_summary(truncated: Sequence[BaseMessage]) -> str:
    extracted_facts: List[str] = []
    for m in truncated:
        c = str(getattr(m, "content", ""))
        sql_m = re.findall(r"(?:SELECT|FROM)\s+([a-zA-Z0-9_]+)", c, re.IGNORECASE)
        if sql_m:
            extracted_facts.append(f"- 涉及物理表: {', '.join(set(sql_m[:3]))}")
        if "涉案" in c or "违规" in c:
            for line in c.split("\n"):
                if any(kw in line for kw in ["涉案", "违规", "总金额", "医疗机构"]) and len(line) < 80:
                    extracted_facts.append(f"- 历史结论: {line.strip()}")
                    break
    facts_block = "\n".join(extracted_facts[:5]) if extracted_facts else "[历史中间会话数据已安全归档至底稿]"
    logger.info("⚡ [TurnHistoryCompactor] 成功完成确定性高保真历史摘要装配，节省 10~15s LLM 延迟！")
    return f"📋 [历史事实高保真确定性摘要 (0ms)]：\n{facts_block}"


def _assemble_compacted_messages(
    system_msgs: List[BaseMessage],
    gssc_msg: Optional[BaseMessage],
    retained_others: List[BaseMessage],
    recent_chat_msgs: List[BaseMessage],
    summary_content: Optional[str] = None,
) -> List[BaseMessage]:
    final_msgs = system_msgs.copy()
    gssc_added = None
    for m in retained_others:
        if m == gssc_msg or "[⚠️ GSSC" in str(getattr(m, "content", "")):
            final_msgs.append(m)
            gssc_added = m
            break
    if summary_content:
        final_msgs.append(SystemMessage(content=summary_content))
    for m in retained_others:
        if m != gssc_added:
            final_msgs.append(m)
    final_msgs.extend(recent_chat_msgs)
    return final_msgs


def compress_messages_by_budget(
    messages: Sequence[BaseMessage],
    max_tokens: int,
    keep_recent_count: int = 10,
    estimate_fn: Callable[[Any], int] = estimate_tokens,
) -> List[BaseMessage]:
    """[Model-Driven Compaction / 确定性事实摘要提炼]"""
    total_tokens = sum(estimate_fn(m.content) for m in messages)
    if total_tokens <= max_tokens:
        return list(messages)

    logger.warning(f"⚠️ [TurnHistoryCompactor] 整合后消息流超限 ({total_tokens} > {max_tokens})，触发确定性摘要重置！")
    system_msgs, gssc_msg, chat_msgs = _partition_messages(messages)
    recent_chat_msgs = chat_msgs[-keep_recent_count:] if len(chat_msgs) > keep_recent_count else chat_msgs
    older_chat_msgs = chat_msgs[:-keep_recent_count] if len(chat_msgs) > keep_recent_count else []

    base_tokens = sum(estimate_fn(m.content) for m in (system_msgs + recent_chat_msgs))
    budget_for_others = max_tokens - base_tokens - 400
    retained_others: List[BaseMessage] = []
    truncated: List[BaseMessage] = []

    if gssc_msg:
        gssc_tokens = estimate_fn(gssc_msg.content)
        if gssc_tokens <= budget_for_others:
            retained_others.append(gssc_msg)
            budget_for_others -= gssc_tokens
        else:
            retained_others.append(SystemMessage(content=str(gssc_msg.content)[:4000] + "\n\n[⚠️ GSSC 载荷过长，部分内容已被物理截断]"))
            budget_for_others = 0

    for m in older_chat_msgs:
        m_t = estimate_fn(m.content)
        if m_t <= budget_for_others:
            retained_others.append(m)
            budget_for_others -= m_t
        else:
            truncated.append(m)

    summary_content = _build_deterministic_summary(truncated) if truncated else None
    return _assemble_compacted_messages(system_msgs, gssc_msg, retained_others, recent_chat_msgs, summary_content)
