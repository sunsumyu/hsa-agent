"""
app/core/context_builder.py
===========================
[V210.0] 工业级上下文构建器 (GSSC Unified Context Builder)

核心职责：
统一管理智能体的上下文生命周期，运行 Gather -> Select -> Structure -> Compress 流水线。
彻底对齐教材 9.3 节《ContextBuilder》标准，结合 PII 隔离、NoteTool 外部便签簿、及 ClickHouse 元数据降级进行硬化。
"""

import os
import math
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from loguru import logger
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

from app.core.schemas import RoleConfigV2
from app.core.context.context_selector import AdaptiveSelector

@dataclass
class ContextPacket:
    """[V210.0] 候选信息包 ── 统一管理异构审计证据"""
    content: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    token_count: int = 0
    relevance_score: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.relevance_score = max(0.0, min(1.0, self.relevance_score))
        if self.token_count <= 0:
            self.token_count = self.estimate_tokens(self.content)

    @staticmethod
    def estimate_tokens(text: Any) -> int:
        """中英混合高精度 Token 估算器"""
        if not text:
            return 0
        if isinstance(text, list):
            # 处理多模态/结构化消息内容列表 [{'type': 'text', 'text': '...'}]
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

        chinese_chars = sum(1 for ch in text if isinstance(ch, str) and '\u4e00' <= ch <= '\u9fff')
        english_words = len([w for w in text.split() if w])
        return int(chinese_chars + english_words * 1.3)


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
    def __init__(self, role_config: RoleConfigV2):
        self.role_config = role_config
        # 弹性 Token 采样上限
        self.max_input_tokens = getattr(role_config, 'max_input_tokens', 4000)
        self.config = ContextConfig(max_tokens=self.max_input_tokens)
        self.selector = AdaptiveSelector()

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
        from app.memory.message_sanitizer import ensure_tool_pairing
        structured_messages = ensure_tool_pairing(structured_messages)

        logger.info(f"✅ [ContextBuilder] GSSC 治理成功！共精选出 {len(selected_packets)} 个黄金上下文信息包。")
        return structured_messages

    def _gather_all(self, query: str, target_tables: List[str], history: List[BaseMessage], metadata: Dict[str, Any]) -> List[ContextPacket]:
        packets = []

        # 0. Gather Semantic Alignment Context (最高优先级，强保留)
        alignment = metadata.get("semantic_alignment")
        if alignment:
            alignment_xml = f"""<semantic_alignment_context>
  <explanation>{alignment.get('explanation', '')}</explanation>
  <disease_keywords>{', '.join(alignment.get('disease_keywords', []))}</disease_keywords>
  <aligned_icd10_codes>{', '.join(alignment.get('aligned_codes', []))}</aligned_icd10_codes>
  <sideloaded_temp_table>{alignment.get('temp_table') or 'None'}</sideloaded_temp_table>
  <baseline_strategy>{alignment.get('baseline_meta', {}).get('strategy', 'NONE')}</baseline_strategy>
  <phase1_baseline_sql>{alignment.get('baseline_meta', {}).get('phase1_baseline_sql', 'None')}</phase1_baseline_sql>
</semantic_alignment_context>"""
            packets.append(ContextPacket(
                content=alignment_xml,
                relevance_score=1.0,
                metadata={"type": "semantic_alignment", "priority": "high"}
            ))

        # 1. Gather ClickHouse Schemas
        try:
            from app.core.registry.schema_registry import schema_registry
            # [V2.0 NEW] 使用场景感知表选择器
            from app.core.scene_table_selector import scene_table_selector

            # 如果没有指定 target_tables，使用场景感知选择
            if not target_tables:
                primary_table, all_tables = scene_table_selector.select_tables(query)
                target_tables = all_tables
                # [V2.0 NEW] 将场景强制提示注入 metadata
                enforcement_hint = scene_table_selector.get_enforcement_hint(query)
                if enforcement_hint:
                    metadata["scene_enforcement"] = enforcement_hint
                    metadata["expected_table"] = primary_table

            tables = target_tables if target_tables else [schema_registry.get_main_table()]
            for table in tables:
                entry = schema_registry.get_table(table)
                if entry:
                    detail_xml = self.selector.schema_to_xml(entry)
                    packets.append(ContextPacket(
                        content=detail_xml,
                        relevance_score=0.9,  # 提高相关性评分
                        metadata={"type": "clickhouse_schema", "table_name": table}
                    ))
        except Exception as e:
            logger.warning(f"⚠️ [ContextBuilder] Gather Schemas 失败: {e}")

        # 2. Gather Cognitive Memories
        try:
            from app.memory.semantic_memory import cognitive_memory_manager
            cognitive_memory_manager._init_components()
            if cognitive_memory_manager.semantic:
                docs = cognitive_memory_manager.semantic.recall_expert_knowledge(query)
                for doc in docs:
                    xml_mem = f'<experience>\n  {doc.page_content}\n</experience>'
                    packets.append(ContextPacket(
                        content=xml_mem,
                        relevance_score=0.7,
                        metadata={"type": "cognitive_memory"}
                    ))
        except Exception as e:
            logger.warning(f"⚠️ [ContextBuilder] Gather Memories 失败: {e}")

        # 3. Gather NoteTool 外部便签簿里程碑 (最高优先级，强保留)
        note_file = "data/audit_notes.md"
        if os.path.exists(note_file):
            try:
                with open(note_file, "r", encoding="utf-8") as f:
                    note_content = f.read().strip()
                if note_content:
                    # [V215.0] 为了防止 Token 爆炸和跨任务交叉污染，我们只加载最近的 3 条便签线索
                    note_parts = [p.strip() for p in note_content.split("---") if p.strip()]
                    recent_notes = note_parts[-3:] if len(note_parts) > 3 else note_parts
                    note_content_cleaned = "\n\n---\n\n".join(recent_notes)
                    
                    logger.info("📓 [ContextBuilder] 成功 Gather 最近 3 条外部审计便签线索")
                    packets.append(ContextPacket(
                        content=note_content_cleaned,
                        relevance_score=1.0,
                        metadata={"type": "note_evidence", "priority": "high"}
                    ))
            except Exception as e:
                logger.warning(f"读取外部便签失败: {e}")

        return packets

    def _select_packets(self, packets: List[ContextPacket], query: str, budget: int) -> List[ContextPacket]:
        # 分离高优先级指令/便签和评估池
        high_priority = [p for p in packets if p.metadata.get("priority") == "high"]
        evaluate_pool = [p for p in packets if p.metadata.get("priority") != "high"]

        high_tokens = sum(p.token_count for p in high_priority)
        remaining_budget = budget - high_tokens

        if remaining_budget <= 0:
            logger.warning("🚨 [ContextBuilder] 高优先级指令/便签已满额物理预算！")
            return high_priority

        scored_pool = []
        for p in evaluate_pool:
            # 1. 关键词 Jaccard 相关度
            rel = self._calculate_jaccard(p.content, query)
            p.relevance_score = rel
            # 2. 指数时间衰减新近度
            rec = self._calculate_time_decay(p.timestamp)
            
            # 综合评分 = 0.7 * 相似度 + 0.3 * 新近度
            combined = self.config.relevance_weight * rel + self.config.recency_weight * rec
            
            if rel >= self.config.min_relevance or p.metadata.get("type") == "clickhouse_schema":
                scored_pool.append((combined, p))

        # 降序排列
        scored_pool.sort(key=lambda x: x[0], reverse=True)

        # 贪心装载
        selected = high_priority.copy()
        current_tokens = high_tokens

        for score, p in scored_pool:
            if current_tokens + p.token_count <= budget:
                selected.append(p)
                current_tokens += p.token_count
            else:
                # 触发 ClickHouse 表结构的弹性退化降级机制！
                if p.metadata.get("type") == "clickhouse_schema":
                    try:
                        from app.core.registry.schema_registry import schema_registry
                        entry = schema_registry.get_table(p.metadata["table_name"])
                        if entry:
                            header_xml = self.selector.schema_to_header_only(entry)
                            header_t = ContextPacket.estimate_tokens(header_xml)
                            if current_tokens + header_t <= budget:
                                selected.append(ContextPacket(
                                    content=header_xml,
                                    relevance_score=p.relevance_score,
                                    metadata=p.metadata
                                ))
                                current_tokens += header_t
                    except Exception as schema_degrade_err:
                        logger.warning(f"Schema 降级处理失败: {schema_degrade_err}")
                else:
                    # 预算饱和，优雅舍弃后续包
                    break

        return selected

    def _calculate_jaccard(self, text: str, query: str) -> float:
        w_text = set(text.lower().split())
        w_query = set(query.lower().split())
        if not w_query:
            return 0.0
        return len(w_text & w_query) / len(w_text | w_query)

    def _calculate_time_decay(self, timestamp: datetime.datetime) -> float:
        age_hours = (datetime.datetime.now() - timestamp).total_seconds() / 3600
        decay_factor = 0.1
        return max(0.1, min(1.0, math.exp(-decay_factor * age_hours)))

    def _structure_into_messages(self, selected: List[ContextPacket], original_history: List[BaseMessage]) -> List[BaseMessage]:
        # 分离出 System 消息和历史聊天记录 (保留消息的原有对象和绝对自然顺序，防止 API 400 校验失效)
        system_msgs = [m for m in original_history if m.type == 'system']
        chat_msgs = [m for m in original_history if m.type != 'system']
        
        schemas, memories, notes, alignments = [], [], [], []

        for p in selected:
            t = p.metadata.get("type")
            if t == "clickhouse_schema":
                schemas.append(p.content)
            elif t == "cognitive_memory":
                memories.append(p.content)
            elif t == "note_evidence":
                notes.append(p.content)
            elif t == "semantic_alignment":
                alignments.append(p.content)

        # 构建干净的事实载荷 XML
        xml_payload = "<context_engineering_payload>\n"
        
        # [V215.1] DDL 物理 Schema 关系到 SQL 编写的生死，必须置于 XML 最前，避免被 Compaction 截断丢失
        if schemas:
            xml_payload += "  <database_schema_context>\n"
            for schema in schemas:
                xml_payload += f"    {schema}\n"
            xml_payload += "  </database_schema_context>\n"

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

        # 组装最终消息链
        final_messages = []
        # 1. 填入初始 System 指令
        final_messages.extend(system_msgs)
        # 2. 将 XML 事实载荷物理隔离地注入系统指令后方 (前置载荷)
        final_messages.append(SystemMessage(content=f"【当前审计黄金上下文载荷 (GSSC 动态精选渲染版)】：\n{xml_payload}"))
        # 3. 填入完整的历史聊天记录 (保证绝对自然顺序留在最尾部)
        final_messages.extend(chat_msgs)
        
        return final_messages

    async def _compress_messages_budget(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        # 对整个消息流执行结构化兜底截断压缩，并应用 Model-Driven Compaction (摘要重置) 机制
        total_tokens = sum(ContextPacket.estimate_tokens(m.content) for m in messages)
        if total_tokens <= self.config.max_tokens:
            return messages

        logger.warning(f"⚠️ [ContextBuilder] 整合后消息流超限 ({total_tokens} > {self.config.max_tokens})，触发 Model-Driven Compaction 摘要重置！")
        
        # 区分消息类型
        system_msgs = []
        gssc_msg = None
        chat_msgs = []

        for m in messages:
            if isinstance(m, SystemMessage) and "【当前审计黄金上下文载荷" in str(getattr(m, "content", "")):
                gssc_msg = m
            elif m.type == 'system':
                system_msgs.append(m)
            else:
                chat_msgs.append(m)

        # 优先保留:
        # 1. 初始 System 消息
        # 2. 最新的 10 个聊天记录 (确保 Agent 的即时交互记忆不丢失)
        keep_recent_count = 10
        recent_chat_msgs = chat_msgs[-keep_recent_count:] if len(chat_msgs) > keep_recent_count else chat_msgs
        older_chat_msgs = chat_msgs[:-keep_recent_count] if len(chat_msgs) > keep_recent_count else []

        # 计算已保留消息的 token
        retained_base = system_msgs + recent_chat_msgs
        base_tokens = sum(ContextPacket.estimate_tokens(m.content) for m in retained_base)

        # 预算分配 (预留约 400 给摘要生成)
        budget_for_others = self.config.max_tokens - base_tokens - 400
        
        gssc_tokens = ContextPacket.estimate_tokens(gssc_msg.content) if gssc_msg else 0

        retained_others = []
        truncated = []

        if gssc_msg:
            if gssc_tokens <= budget_for_others:
                retained_others.append(gssc_msg)
                budget_for_others -= gssc_tokens
            else:
                # GSSC 载荷太大，物理截断它
                truncated_gssc = SystemMessage(
                    content=str(gssc_msg.content)[:4000] + "\n\n[⚠️ GSSC 载荷过长，部分内容已被物理截断]"
                )
                retained_others.append(truncated_gssc)
                budget_for_others = 0

        # 对 older_chat_msgs 进行装载或截断
        for m in older_chat_msgs:
            m_t = ContextPacket.estimate_tokens(m.content)
            if m_t <= budget_for_others:
                retained_others.append(m)
                budget_for_others -= m_t
            else:
                truncated.append(m)

        if not truncated:
            final_msgs = system_msgs.copy()
            gssc_added = None
            for m in retained_others:
                if m == gssc_msg or "[⚠️ GSSC" in str(getattr(m, "content", "")):
                    final_msgs.append(m)
                    gssc_added = m
                    break
            for m in retained_others:
                if m != gssc_added:
                    final_msgs.append(m)
            final_msgs.extend(recent_chat_msgs)
            return final_msgs

        # 收集被截断消息的文本内容进行摘要蒸馏
        truncated_text = "\n".join(f"[{m.type}]: {str(m.content)[:500]}" for m in truncated)
        
        summary_content = "[⚠️ 较早的历史事实载荷超出预算，已被物理截断]"
        try:
            from app.core.llm_provider import llm_provider
            summary_prompt = (
                f"你是一个资深的医保稽核审计专家。以下部分较早的审计线索和对话历史因为 Token 预算超限即将被物理截断。\n"
                f"请你用最精简、凝练的语言（不超过 150 字），总结这段被截断历史中的**核心 SQL 语句、查询表名、核心核查规则及中间结论**，以便智能体恢复审计状态：\n\n"
                f"【被截断的历史事实】：\n{truncated_text}\n\n"
                f"请直接给出高保真审计摘要，不要有任何客套话："
            )
            # 使用快速轻量级模型进行高速摘要生成
            response = await llm_provider.chat(
                role="reporter", 
                messages=[HumanMessage(content=summary_prompt)],
                model_id="LIGHT"
            )
            summary_content = f"📋 [被截断历史事实的高保真 Compaction 摘要]：\n{str(response.content).strip()}"
            logger.info("⚡ [ContextBuilder] 成功完成 Model-Driven Compaction 历史摘要重置！")
        except Exception as summary_err:
            logger.warning(f"⚠️ [ContextBuilder] 摘要蒸馏失败，降级为物理截断: {summary_err}")
            # 降级截断处理
            summary_content = f"[⚠️ 较早数据超出预算，已被物理降级截断] (截断内容包含: {', '.join(m.type for m in truncated[:3])} 等)"

        # 拼装最终结果：
        # system_msgs -> GSSC (或截断GSSC) -> 摘要 -> 剩下的 older 消息 -> recent_chat_msgs
        final_msgs = system_msgs.copy()
        
        gssc_added = None
        for m in retained_others:
            if m == gssc_msg or "[⚠️ GSSC" in getattr(m, "content", ""):
                final_msgs.append(m)
                gssc_added = m
                break
                
        final_msgs.append(SystemMessage(content=summary_content))
        
        for m in retained_others:
            if m != gssc_added:
                final_msgs.append(m)
                
        final_msgs.extend(recent_chat_msgs)
        return final_msgs

