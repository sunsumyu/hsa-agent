"""
app/core/context/context_payload_renderer.py
============================================
[Matt Pocock Deep Module] 上下文结构化载荷装配与前缀缓存渲染器

核心职责：
1. 构建严格符合 Prefix Cache 共享对齐的 XML 事实载荷（DDL 最先，动态实体居后）
2. 物理剔除前序多轮对话中已注入的脏 GSSC 载荷，防止 Schema 递归指数级膨胀
3. 装配 System 初始指令流、带有 ephemeral cache_control 的事实载荷及已治理的聊天记录
"""

from __future__ import annotations

from typing import Any, List
from langchain_core.messages import BaseMessage, SystemMessage

from app.core.context.turn_history_compactor import compact_past_turns


class ContextPayloadRenderer:
    """事实载荷 XML 组装与前缀缓存消息流装配器深模块"""

    def build_xml_payload(self, selected_packets: List[Any]) -> str:
        """构建干净的事实载荷 XML (按静态程度升序排列以最大化模型 KV 前缀缓存命中率)"""
        schemas, memories, notes, alignments, enforcements = [], [], [], [], []

        for p in selected_packets:
            t = p.metadata.get("type")
            if t == "scene_enforcement":
                enforcements.append(p.content)
            elif t == "clickhouse_schema":
                schemas.append(p.content)
            elif t == "cognitive_memory":
                memories.append(p.content)
            elif t == "note_evidence":
                notes.append(p.content)
            elif t == "semantic_alignment":
                alignments.append(p.content)

        xml_payload = "<context_engineering_payload>\n"

        # [Prefix Cache 关键对齐] DDL 物理 Schema 占 70%~90% Token，严格置于最顶部
        if schemas:
            xml_payload += "  <database_schema_context>\n"
            for schema in schemas:
                xml_payload += f"    {schema}\n"
            xml_payload += "  </database_schema_context>\n"

        # 相对静态的场景与表契约规则
        if enforcements:
            xml_payload += "  <mandatory_table_enforcements>\n"
            for enf in enforcements:
                xml_payload += f"    {enf}\n"
            xml_payload += "  </mandatory_table_enforcements>\n"

        # 动态内容后置：防止每个 Case 独特的医学实体词/策略破坏前置 DDL 缓存
        if alignments:
            for align in alignments:
                xml_payload += f"  {align}\n"

        if memories:
            xml_payload += "  <experiential_context>\n"
            for mem in memories:
                xml_payload += f"    {mem}\n"
            xml_payload += "  </experiential_context>\n"

        if notes:
            xml_payload += "  <structured_audit_notes>\n"
            for note in notes:
                xml_payload += f"    {note}\n"
            xml_payload += "  </structured_audit_notes>\n"

        xml_payload += "</context_engineering_payload>"
        return xml_payload

    def render(
        self,
        selected_packets: List[Any],
        original_history: List[BaseMessage],
    ) -> List[BaseMessage]:
        """组装完整的消息链"""
        # 过滤前序轮次已注入的 GSSC 上下文载荷，严防多轮重试导致 Schema 载荷指数倍增
        system_msgs = [
            m for m in original_history
            if m.type == "system"
            and "【当前审计黄金上下文载荷" not in str(getattr(m, "content", ""))
            and "<context_engineering_payload>" not in str(getattr(m, "content", ""))
        ]
        chat_msgs = [m for m in original_history if m.type != "system"]

        xml_payload = self.build_xml_payload(selected_packets)

        final_messages = []
        # 1. 填入初始 System 指令
        final_messages.extend(system_msgs)

        # 2. 将 XML 事实载荷物理隔离地注入系统指令后方并挂载 cache_control
        final_messages.append(
            SystemMessage(
                content=f"【当前审计黄金上下文载荷 (GSSC 动态精选渲染版)】：\n{xml_payload}",
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            )
        )

        # 3. 对历史聊天记录进行会话级治理
        compacted_chat = compact_past_turns(chat_msgs)
        final_messages.extend(compacted_chat)

        return final_messages


# 单例默认实例
context_payload_renderer = ContextPayloadRenderer()
