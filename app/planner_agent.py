"""
app/planner_agent.py
====================
[V150.0] 审计规划智能体 (Planner Agent)

负责：
1. 语义缓存拦截：识别已解决的重复问题。
2. 快速路由分流：将标准规则任务导向确定性算子。
3. 动态审计规划：根据问题复杂度（Heavy/Light）执行任务拆解与方法论构建。
"""

from typing import Dict, Any, List, Optional
import re
import os
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.model_manager import model_manager
from app.core.memory import memory_hub
from app.neo4j_manager import neo4j_manager
from app.fast_router import fast_router, RouteType
from app.prompts import PLANNER_PROMPT
from app.structured_tracer import StructuredTracer

class AuditPlannerAgent:
    def __init__(self):
        pass

    async def plan(self, state: Dict[str, Any], config: Any) -> Dict[str, Any]:
        """执行全路径规划逻辑 [V171.1]"""
        # 初始化结构化追踪器
        tracer = StructuredTracer(
            session_id=state.get("session_id", "default"),
            on_event_cb=getattr(config, "on_trace_update", None)
        )
        
        user_input = ""
        # 提取用户输入
        for msg in state.get("messages", []):
            if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
                user_input = msg[1] if isinstance(msg, tuple) else str(msg.content)
                break
        
        if not user_input:
            return {"error_log": "未获取到用户审计需求", "tasks": []}

        # 1. 语义缓存检查 (Action Compression)
        with tracer.span("CACHE_CHECK", node="PLANNER") as span:
            from app.semantic_memory import action_cache_manager
            disable_cache = os.getenv("DISABLE_AUDIT_CACHE", "false").lower() == "true"
            cached_plan = None if disable_cache else action_cache_manager.search(user_input)
            if cached_plan:
                logger.success("⚡ [Planner] 命中动作链缓存，实现毫秒级路径压缩")
                span.set_result("命中经验缓存")
                return {
                    "tasks": cached_plan.get("tasks", ["执行已验证的精准 SQL"]),
                    "methodology": cached_plan.get("methodology", "基于历史成功经验的快速路径"),
                    "sql_query": cached_plan.get("sql"),
                    "sql_history": [cached_plan.get("sql")] if cached_plan.get("sql") else [], # [V178.9] 确保缓存路径也具备证据链
                    "cache_hit": True,
                    "execution_trace": tracer.to_legacy_list(),
                    "messages": []
                }
            span.set_result("未命中缓存")

        # 2. Fast Route 快速路由
        route = fast_router.classify(user_input)
        if route.route_type != RouteType.UNKNOWN:
            logger.success(f"🚀 [Planner] 命中快速路由 [{route.target_id}]")
            task_desc = f"使用 audit_medical_rule 工具，规则ID: {route.target_id}" if route.route_type == RouteType.KNOWN_RULE else f"使用 run_anomaly_detection 工具，算法ID: {route.target_id}"
            
            return {
                "tasks": [task_desc],
                "metadata": {
                    "fast_route_id": route.target_id,
                    "fast_route_type": route.route_type.value,
                    "extra_filters": route.extra_filters,
                    "user_question": user_input,
                },
                "retry_count": 0,
                "messages": []
            }

        # 3. LLM 动态规划路径
        with tracer.span("LLM_PLANNING", node="PLANNER") as span:
            from app.core.llm_provider import llm_provider
            
            # [V168.1] 使用 state 中已持久化的复杂度或重新计算
            complexity = (state.get("metadata") or {}).get("model_id", "HEAVY")
            role = "planner_heavy" if complexity == "HEAVY" else "planner_light"

            # [V178.9] 准备上下文：混合检索 (Semantic + Episodic)
            ontology = neo4j_manager.get_ontology()
            
            # [V180.0] 意图强化：扩展医学关键词，防止语义丢失
            from app.neo4j_manager import expand_medical_intent
            expanded_terms = expand_medical_intent(user_input)
            if expanded_terms:
                logger.info(f"🧬 [IntentEnrich] 扩展医学意图: {expanded_terms}")
                user_input_enriched = f"{user_input} (核查范围应包含但不限于: {', '.join(expanded_terms)})"
            else:
                user_input_enriched = user_input

            # 1. 语义召回 (Schema/行业知识)
            relevant_items = await memory_hub.query(user_input_enriched)
            schema_hint = memory_hub.semantic.format_for_prompt(relevant_items)
            avoidance_guide = memory_hub.semantic.get_avoidance_guides(user_input_enriched)
            if avoidance_guide: schema_hint = f"{schema_hint}\n\n{avoidance_guide}"

            # 2. 情景召回 (历史成功案例)
            episodes = await memory_hub.episodic.recall_experience(user_input_enriched, limit=2)
            experience_hint = memory_hub.episodic.format_experience_for_prompt(episodes)

            # 3. 构造 Messages
            messages = PLANNER_PROMPT.format_messages(
                original_question=user_input_enriched[:600],
                messages=state["messages"], 
                experiences=experience_hint, 
                ontology=ontology,
                schema_info=schema_hint
            )
            
            # 调用统一 Provider
            response = await llm_provider.chat(
                role=role,
                messages=messages,
                config=config,
                state=state
            )
            
            content = str(response.content)

            # 解析响应
            methodology = ""
            tasks = []
            if "### METHODOLOGY" in content:
                parts = content.split("### TASKS")
                methodology = parts[0].replace("### METHODOLOGY", "").strip()
                if len(parts) > 1:
                    task_part = parts[1].strip()
                    tasks = [re.sub(r'^[\-\*123\.]\s*', '', line).strip() for line in task_part.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3."))]
            else:
                tasks = [re.sub(r'^[\-\*123\.]\s*', '', line).strip() for line in content.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3."))]
            
            span.set_result(f"完成路径规划，生成任务 {len(tasks)} 条")

        return {
            "tasks": tasks[:3], 
            "methodology": methodology,
            "messages": [response], 
            "retry_count": 0, 
            "execution_trace": tracer.to_legacy_list()
        }

# 单例导出
planner_agent = AuditPlannerAgent()
