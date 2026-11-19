# app/core/observability/session_manager.py
# -*- coding: utf-8 -*-
"""
app/core/observability/session_manager.py
========================================
[会话生命周期与上下文膨胀治理]
- 针对 LangSmith Threads 会话聚合提供细粒度 RunnableConfig (turn:X, multi-turn-audit, thread_id)
- 针对多轮长会话实行防上下文膨胀的动态截断与摘要压缩 (compact_history_if_needed)
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


class SessionContextManager:
    """[会话生命周期治理] 管理 Threads 聚合元数据与长对话上下文压缩"""

    @classmethod
    def build_turn_config(
        cls,
        session_id: str,
        turn_index: int,
        action_name: str,
        extra_meta: Optional[Dict[str, Any]] = None,
        base_config: Optional[RunnableConfig] = None
    ) -> RunnableConfig:
        """
        构造单轮对话的 LangSmith/LangChain 运行配置。
        注入 run_name, thread_id, tags 及轮次元数据。
        """
        cfg = base_config.copy() if base_config else {}
        cfg["run_name"] = f"Audit-Turn-{turn_index}: {action_name}"

        tags = list(cfg.get("tags") or [])
        tags.extend([f"turn:{turn_index}", "multi-turn-audit"])
        # 去重并保持插入顺序
        cfg["tags"] = list(dict.fromkeys(tags))

        meta = dict(cfg.get("metadata") or {})
        meta.update({
            "session_id": session_id,
            "turn": turn_index,
            **(extra_meta or {})
        })
        cfg["metadata"] = meta

        configurable = dict(cfg.get("configurable") or {})
        configurable["thread_id"] = session_id
        cfg["configurable"] = configurable
        return cfg

    @classmethod
    def compact_history_if_needed(
        cls,
        history: List[BaseMessage],
        max_retained_turns: int = 4
    ) -> List[BaseMessage]:
        """
        上下文膨胀治理：
        若对话轮数超过 max_retained_turns，保留首部系统人设 (SystemMessage) 与最近 max_retained_turns 轮，
        将中间过期的多轮问答折叠压缩为单一系统摘要消息。
        """
        if not history:
            return []

        system_msg = history[0] if isinstance(history[0], SystemMessage) else None
        dialogue_msgs = history[1:] if system_msg else history

        # 每一轮假定包含 1 Human + 1 AI (共 2 条消息)
        retained_msg_count = max_retained_turns * 2
        if len(dialogue_msgs) <= retained_msg_count:
            return history

        older_msgs = dialogue_msgs[:-retained_msg_count]
        recent_msgs = dialogue_msgs[-retained_msg_count:]

        # 压缩早期历史
        summary_snippets = []
        for m in older_msgs:
            prefix = "审计员" if getattr(m, "type", "") == "human" else "AI助手"
            content_str = str(m.content) if m.content is not None else ""
            snippet = content_str[:40].replace("\n", " ")
            summary_snippets.append(f"- {prefix}: {snippet}...")

        summary_msg = SystemMessage(
            content="【前置多轮审计问答摘要】:\n" + "\n".join(summary_snippets)
        )

        result = []
        if system_msg:
            result.append(system_msg)
        result.append(summary_msg)
        result.extend(recent_msgs)
        return result
