"""
app/agents/planner_context_assembler.py
=======================================
[Matt Pocock Deep Module & SSOT]
审计规划智能体 (Planner Agent) 上下文组装与轻重提示词装配器。

核心职责：
1. 意图强化：通过 Neo4j 图谱本体自动扩展医学关键词 (expand_medical_intent)
2. 轻重模型提示词差异化生成 (planner_heavy 委托 GSSC 统一引擎，planner_light 极简轻量内存检索)
3. 结构化 Messages 渲染 (PLANNER_PROMPT.format_messages)
4. 规划产物紧凑化裁剪 (限制方法论 300 字符，关键任务前 3 条，防 Token 滚雪球)
5. 端到端 PlannerContextPayload 装配
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from langchain_core.messages import BaseMessage, AIMessage

from app.core.memory import memory_hub
from app.infra.neo4j_manager import neo4j_manager, expand_medical_intent
from app.prompts import PLANNER_PROMPT


@dataclass
class PlannerContextPayload:
    """Planner 上下文装配产物契约"""
    role: str
    prompt_messages: List[BaseMessage]
    user_input_enriched: str
    ontology: str
    schema_hint: str
    experience_hint: str


def enrich_user_intent(user_input: str) -> str:
    """
    [V180.0] 意图强化：扩展医学关键词，防止语义丢失。
    """
    try:
        expanded_terms = expand_medical_intent(user_input)
    except Exception as e:
        logger.warning(f"Neo4j 意图扩展异常: {e}")
        expanded_terms = []

    if expanded_terms:
        logger.info(f"🧬 [IntentEnrich] 扩展医学意图: {expanded_terms}")
        return f"{user_input} (核查范围应包含但不限于: {', '.join(expanded_terms)})"
    return user_input


async def assemble_planner_hints(role: str, user_input_enriched: str) -> Tuple[str, str]:
    """
    根据模型角色 (planner_heavy vs planner_light) 生成 Schema 提示与经验提示。
    - planner_heavy: 提示已由统一 GSSC 挂载于消息流尾部，免除重复 IO
    - planner_light: 执行极简内存查询以防爆 Token
    """
    if role == "planner_heavy":
        schema_hint = (
            "【已启用 GSSC 统一引擎：相关的 ClickHouse DDL 与物理主表元数据规范，"
            "已安全挂载于当前消息流最尾部。请滚动至尾部查阅 <database_schema_context> 标签获取真实物理 Schema 以确保规划的准确性】"
        )
        experience_hint = (
            "【已启用 GSSC 统一引擎：相关的专家审计经验与已固化的外部便签证据线索，"
            "已安全挂载于当前消息流最尾部。请滚动至尾部查阅 <experiential_context> 与 <structured_audit_notes> 获取细节】"
        )
        return schema_hint, experience_hint

    # planner_light 模式
    relevant_items = await memory_hub.query(user_input_enriched)
    schema_hint = memory_hub.semantic.format_for_prompt(relevant_items)
    avoidance_guide = memory_hub.semantic.get_avoidance_guides(user_input_enriched)
    if avoidance_guide:
        schema_hint = f"{schema_hint}\n\n{avoidance_guide}"

    episodes = await memory_hub.episodic.recall_experience(user_input_enriched, limit=2)
    experience_hint = memory_hub.episodic.format_experience_for_prompt(episodes)

    return schema_hint, experience_hint


def build_planner_prompt(
    user_input_enriched: str,
    messages: List[BaseMessage],
    schema_hint: str,
    experience_hint: str,
    ontology: str
) -> List[BaseMessage]:
    """
    渲染结构化 PLANNER_PROMPT 提示词。
    """
    return PLANNER_PROMPT.format_messages(
        original_question=user_input_enriched[:600],
        messages=messages,
        experiences=experience_hint,
        ontology=ontology,
        schema_info=schema_hint
    )


def format_compact_plan_message(methodology: str, tasks: List[str]) -> AIMessage:
    """
    [V220.0 Matt Pocock 局部性优化]
    向后序 Coder 仅传递精简紧凑的规划决策，彻底阻断上下文滚雪球。
    """
    compact_plan_text = (
        f"【审计规划指引】\n核心方法论：{methodology[:300]}\n关键任务清单：\n"
        + "\n".join(f"- {t}" for t in tasks[:3])
    )
    return AIMessage(content=compact_plan_text)


async def assemble_planner_context(
    state: Dict[str, Any],
    user_input: str
) -> PlannerContextPayload:
    """
    顶层装配入口：为 AuditPlannerAgent 提供自包含的 Prompt Payload。
    """
    complexity = (state.get("metadata") or {}).get("model_id", "HEAVY")
    role = "planner_heavy" if complexity == "HEAVY" else "planner_light"

    # 1. 意图强化
    user_input_enriched = enrich_user_intent(user_input)

    # 2. 混合检索与提示词装配
    ontology = neo4j_manager.get_ontology()
    schema_hint, experience_hint = await assemble_planner_hints(role, user_input_enriched)

    # 3. 构造 Messages
    messages = state.get("messages", [])
    prompt_messages = build_planner_prompt(
        user_input_enriched=user_input_enriched,
        messages=messages,
        schema_hint=schema_hint,
        experience_hint=experience_hint,
        ontology=ontology
    )

    return PlannerContextPayload(
        role=role,
        prompt_messages=prompt_messages,
        user_input_enriched=user_input_enriched,
        ontology=ontology,
        schema_hint=schema_hint,
        experience_hint=experience_hint
    )
