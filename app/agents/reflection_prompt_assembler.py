"""
[SPEC-227 / Matt Pocock Deep Module] 审计反思 Prompt 装配深模块 (Reflection Prompt Assembler)

专职负责消解命题提取、执行数据截断治理与反思 Prompt 上下文组装。
"""

from __future__ import annotations
from typing import Any, List, Mapping
from langchain_core.messages import BaseMessage
from app.core.sql_evidence_resolver import resolve_user_query
from app.core.prompts import CRITIC_PROMPT


class ReflectionPromptAssembler:
    """反思 Prompt 装配器深模块：专职负责反思消息上下文组装与数据截断治理。"""

    def __init__(self, max_raw_data_chars: int = 1000, max_context_messages: int = 2):
        self.max_raw_data_chars = max_raw_data_chars
        self.max_context_messages = max_context_messages

    def assemble_critic_messages(self, state: Mapping[str, Any]) -> List[BaseMessage]:
        all_msgs = state.get("messages", [])

        # [SPEC-227 SSOT] 优先提取当前轮次消解后的命题，严禁首项正向死锁
        original_q = resolve_user_query(
            state,
            messages=all_msgs,
            max_chars=300,
            fallback_keys=["user_prompt", "user_query", "human_input", "question"],
        ) or "未获取到原始问题"

        # 只取最近 N 条消息作为反思上下文，减少 Token 浪费
        critic_msgs = (
            all_msgs[-self.max_context_messages:]
            if len(all_msgs) > self.max_context_messages
            else all_msgs
        )

        raw_data = str(state.get("raw_data") or "无数据")
        truncated_raw_data = raw_data[: self.max_raw_data_chars]

        return CRITIC_PROMPT.format_messages(
            original_question=original_q,
            methodology=state.get("methodology", "未定义协议"),
            raw_data=truncated_raw_data,
            error_log=state.get("error_log", "无报错日志"),
            messages=critic_msgs,
        )
