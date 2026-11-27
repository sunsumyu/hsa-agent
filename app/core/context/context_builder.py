"""
app/core/context_builder.py
===========================
[V210.0] 工业级上下文构建器 (GSSC Unified Context Builder)

核心职责：
统一管理智能体的上下文生命周期，运行 Gather -> Select -> Structure -> Compress 流水线。
彻底对齐教材 9.3 节《ContextBuilder》标准，结合 PII 隔离、NoteTool 外部便签簿、及 ClickHouse 元数据降级进行硬化。
"""

import os
import re
import math
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from loguru import logger
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

from app.core.schemas import RoleConfigV2
from app.core.context.context_selector import AdaptiveSelector

from app.core.context.turn_history_compactor import (
    estimate_tokens as _estimate_tokens_fn,
    compact_past_turns as _compact_past_turns_fn,
    compress_messages_by_budget as _compress_messages_by_budget_fn,
)
from app.core.context.context_budget_scheduler import ContextBudgetScheduler, context_budget_scheduler
from app.core.context.context_payload_renderer import ContextPayloadRenderer, context_payload_renderer

@dataclass
class ContextPacket:
    """[V210.0] 候选信息包 ── 统一管理异构审计证据"""
    content: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    token_count: int = 0
    relevance_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.relevance_score is not None:
            self.relevance_score = max(0.0, min(1.0, self.relevance_score))
        if self.token_count <= 0:
            self.token_count = self.estimate_tokens(self.content)

    @staticmethod
    def estimate_tokens(text: Any) -> int:
        """中英混合高精度 Token 估算器（委托至 turn_history_compactor 深模块）"""
        return _estimate_tokens_fn(text)


@dataclass
class ContextConfig:
    """[V210.0] 上下文控制策略配置 ── 动态预算安全阀"""
    max_tokens: int = 4000
    reserve_ratio: float = 0.2         # 预留 20% 空间防爆
    min_relevance: float = 0.15        # 过滤相关性低于 0.15 的噪声
    enable_compression: bool = True
    recency_weight: float = 0.3        # 新近度权重
    relevance_weight: float = 0.7      # 相似度权重

    def __post_init__(self):
        assert 0.0 <= self.reserve_ratio <= 0.5, "安全预留比例不得超过 50%"
        assert abs(self.recency_weight + self.relevance_weight - 1.0) < 1e-6, "权重之和必须为 1.0"


class ContextBuilder:
    def __init__(self, role_config: Optional[RoleConfigV2] = None):
        if role_config is None:
            from app.core.schemas import RoleConfigV2
            role_config = RoleConfigV2(pool="primary", max_input_tokens=4000)
        self.role_config = role_config
        # 弹性 Token 采样上限
        self.max_input_tokens = getattr(role_config, 'max_input_tokens', 4000)
        self.config = ContextConfig(max_tokens=self.max_input_tokens)
        self.selector = AdaptiveSelector()
        self.budget_scheduler = ContextBudgetScheduler(config=self.config)
        self.payload_renderer = context_payload_renderer

    async def build_optimal_context(
        self, 
        user_query: str, 
        history: List[BaseMessage], 
        metadata: Dict[str, Any]
    ) -> List[BaseMessage]:
        """
        [V210.0] 对齐教材的 GSSC 核心执行逻辑：
        1. Gather: 收集系统指令、ClickHouse 物理 Schema、Cognitive Memory 经验、ReAct 聊天历史以及 NoteTool 外部便签。
        2. Select: 根据相关性(Jaccard)与新近度(指数衰减)，在 Token 预算内弹性精选，Note 证据强保留。
        3. Structure: 将精选数据打包进标准化 XML 事实层，与指令层和聊天历史完美隔离。
        4. Compress: 执行结构分区感知式兜底截断压缩。
        """
        logger.info(f"🔄 [ContextBuilder] 开始运行 V210.0 GSSC 上下文治理流水线 (预算限制: {self.max_input_tokens} tokens)...")

        # 1. Gather (收集异构信息包)
        target_tables = metadata.get("target_tables", [])
        packets = self._gather_all(user_query, target_tables, history, metadata)

        # 2. Select (评分排序与预算裁剪)
        # 为高优先级（System + Note）预留空间，贪心选择其他 Packet
        available_budget = int(self.max_input_tokens * (1.0 - self.config.reserve_ratio))
        selected_packets = self._select_packets(packets, user_query, available_budget)

        # 3. Structure (结构化分区隔离)
        # 我们保留 System 消息和聊天历史的自然流，将 XML 事实载荷作为干净 of SystemMessage 物理隔离地追加到消息流尾部！
        structured_messages = self._structure_into_messages(selected_packets, history)

        # 4. Compress (兜底压缩保护)
        # 如果最终生成的整个消息链 Token 依然超过最大预算，触发分区感知式压缩
        if self.config.enable_compression:
            structured_messages = await self._compress_messages_budget(structured_messages)

        # 5. Pairing Guard (工具调用配对安全网)
        from app.core.memory.message_sanitizer import ensure_tool_pairing
        structured_messages = ensure_tool_pairing(structured_messages)

        logger.info(f"✅ [ContextBuilder] GSSC 治理成功！共精选出 {len(selected_packets)} 个黄金上下文信息包。")
        return structured_messages

    def _gather_semantic_alignment_packets(self, metadata: Dict[str, Any]) -> List[ContextPacket]:
        """收集高优先级的语义对齐上下文信息包。"""
        alignment = metadata.get("semantic_alignment")
        if not alignment:
            return []
        alignment_xml = f"""<semantic_alignment_context>
  <explanation>{alignment.get('explanation', '')}</explanation>
  <disease_keywords>{', '.join(alignment.get('disease_keywords', []))}</disease_keywords>
  <aligned_icd10_codes>{', '.join(alignment.get('aligned_codes', []))}</aligned_icd10_codes>
  <sideloaded_temp_table>{alignment.get('temp_table') or 'None'}</sideloaded_temp_table>
  <baseline_strategy>{alignment.get('baseline_meta', {}).get('strategy', 'NONE')}</baseline_strategy>
  <phase1_baseline_sql>{alignment.get('baseline_meta', {}).get('phase1_baseline_sql', 'None')}</phase1_baseline_sql>
</semantic_alignment_context>"""
        return [
            ContextPacket(
                content=alignment_xml,
                relevance_score=1.0,
                metadata={"type": "semantic_alignment", "priority": "high"},
            )
        ]

    def _gather_schema_packets(
        self, query: str, target_tables: List[str], metadata: Dict[str, Any]
    ) -> List[ContextPacket]:
        """收集场景表选择策略与确定性排序后的 ClickHouse Schema 包。"""
        packets: List[ContextPacket] = []
        try:
            from app.core.registry.schema_registry import schema_registry
            from app.core.scene_table_selector import scene_table_selector

            resolved_tables = target_tables
            if not resolved_tables:
                primary_table, all_tables = scene_table_selector.select_tables(query)
                resolved_tables = all_tables
                enforcement_hint = scene_table_selector.get_enforcement_hint(query)
                if enforcement_hint:
                    metadata["scene_enforcement"] = enforcement_hint
                    metadata["expected_table"] = primary_table
                    packets.append(ContextPacket(
                        content=f"<table_selection_policy>\n{enforcement_hint.strip()}\n</table_selection_policy>",
                        relevance_score=1.0,
                        metadata={"type": "scene_enforcement", "priority": "high"},
                    ))
            elif "scene_enforcement" in metadata:
                packets.append(ContextPacket(
                    content=f"<table_selection_policy>\n{metadata['scene_enforcement'].strip()}\n</table_selection_policy>",
                    relevance_score=1.0,
                    metadata={"type": "scene_enforcement", "priority": "high"},
                ))

            main_tbl = schema_registry.get_main_table()
            candidate_tables = resolved_tables if resolved_tables else [main_tbl]
            sorted_tables = ([main_tbl] if main_tbl in candidate_tables else []) + [
                t for t in sorted(set(candidate_tables)) if t != main_tbl
            ]

            for idx, table in enumerate(sorted_tables):
                entry = schema_registry.get_table(table)
                if not entry:
                    continue
                detail_xml = (
                    self.selector.schema_to_xml(entry)
                    if idx < 2
                    else self.selector.schema_to_header_only(entry)
                )
                packets.append(ContextPacket(
                    content=detail_xml,
                    relevance_score=1.0 if idx == 0 else 0.8,
                    metadata={"type": "clickhouse_schema", "table_name": table, "priority": "high" if idx == 0 else "medium"},
                ))
        except Exception as e:
            logger.warning(f"⚠️ [ContextBuilder] Gather Schemas 失败: {e}")
        return packets

    def _gather_cognitive_memory_packets(self, query: str) -> List[ContextPacket]:
        """从语义认知记忆库召回相关专家知识条目。"""
        packets: List[ContextPacket] = []
        try:
            from app.core.memory.semantic_memory import cognitive_memory_manager
            cognitive_memory_manager._init_components()
            if cognitive_memory_manager.semantic:
                for doc in cognitive_memory_manager.semantic.recall_expert_knowledge(query):
                    packets.append(ContextPacket(
                        content=f"<experience>\n  {doc.page_content}\n</experience>",
                        relevance_score=0.7,
                        metadata={"type": "cognitive_memory"},
                    ))
        except Exception as e:
            logger.warning(f"⚠️ [ContextBuilder] Gather Memories 失败: {e}")
        return packets

    def _gather_experience_and_note_packets(self, query: str) -> List[ContextPacket]:
        """在非隔离模式下召回黄金 SQL 经验范例与外部审计便签线索。"""
        is_isolated_mode = (
            os.getenv("DISABLE_AUDIT_CACHE", "false").lower() == "true"
            or os.getenv("IS_BENCHMARK_MODE", "false").lower() == "true"
        )
        if is_isolated_mode:
            return []

        packets: List[ContextPacket] = []
        try:
            from app.core.memory.experience import experience_manager
            golden_exp = experience_manager.get_relevant_experience([query], k=1)
            if golden_exp:
                packets.append(ContextPacket(
                    content=f"<golden_sql_example>\n{golden_exp}\n</golden_sql_example>",
                    relevance_score=0.85,
                    metadata={"type": "golden_sql_experience"},
                ))
        except Exception as e:
            logger.debug(f"[ContextBuilder] Gather Golden Experience 跳过: {e}")

        from app.skills.federated.audit_note_store import audit_note_store
        recent_notes = audit_note_store.read_relevant_notes(query=query, limit=3)
        if recent_notes:
            logger.info("📓 [ContextBuilder] 成功 Gather 高优/相关外部审计便签线索")
            packets.append(ContextPacket(
                content="\n\n---\n\n".join(recent_notes),
                relevance_score=1.0,
                metadata={"type": "note_evidence", "priority": "high"},
            ))
        return packets

    def _gather_all(self, query: str, target_tables: List[str], history: List[BaseMessage], metadata: Dict[str, Any]) -> List[ContextPacket]:
        """收集多源上下文候选信息包。"""
        packets: List[ContextPacket] = []
        packets.extend(self._gather_semantic_alignment_packets(metadata))
        packets.extend(self._gather_schema_packets(query, target_tables, metadata))
        packets.extend(self._gather_cognitive_memory_packets(query))
        packets.extend(self._gather_experience_and_note_packets(query))
        return packets

    def _select_packets(self, packets: List[ContextPacket], query: str, budget: int) -> List[ContextPacket]:
        """[V210.0 Deep Module] 预算评分排序与贪心装载（委托至 ContextBudgetScheduler 深模块）"""
        return self.budget_scheduler.schedule(
            packets=packets,
            query=query,
            budget=budget,
            schema_selector=self.selector,
        )

    def _calculate_jaccard(self, text: str, query: str) -> float:
        """计算词法 Jaccard 相似度（向后兼容委托）"""
        return self.budget_scheduler._calculate_jaccard(text, query)

    def _calculate_time_decay(self, timestamp: datetime.datetime) -> float:
        """计算新近度时间衰减（向后兼容委托）"""
        return self.budget_scheduler._calculate_time_decay(timestamp)

    def _structure_into_messages(self, selected: List[ContextPacket], original_history: List[BaseMessage]) -> List[BaseMessage]:
        """[V210.0 Deep Module] 事实载荷 XML 组装与前缀缓存装配（委托至 ContextPayloadRenderer 深模块）"""
        return self.payload_renderer.render(selected, original_history)

    def _compact_past_turns(self, chat_msgs: List[BaseMessage]) -> List[BaseMessage]:
        """[V228.0 SPEC-227] 会话级长链上下文治理（委托至 turn_history_compactor 深模块）"""
        return _compact_past_turns_fn(chat_msgs)

    async def _compress_messages_budget(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """对整个消息流执行结构化兜底截断压缩（委托至 turn_history_compactor 深模块）"""
        return _compress_messages_by_budget_fn(
            messages=messages,
            max_tokens=self.config.max_tokens,
            estimate_fn=ContextPacket.estimate_tokens,
        )

