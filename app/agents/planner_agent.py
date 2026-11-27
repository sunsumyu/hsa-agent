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

from app.skills.federated.fast_router import fast_router, RouteType
from app.core.structured_tracer import StructuredTracer
from app.core.sql_evidence_resolver import resolve_user_query
from app.agents.planner_evaluator import evaluate_action_cache, parse_planner_response
from app.agents.planner_context_assembler import (
    assemble_planner_context,
    format_compact_plan_message,
)
from app.core.llm_provider import llm_provider

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
        
        # [SPEC-227 SSOT] 优先读取当前轮次确定性命题，废除正向遍历首条提问的锁死缺陷
        user_input = resolve_user_query(state)

        if not user_input:
            return {"error_log": "未获取到用户审计需求", "tasks": []}

        # 1. 语义缓存检查 (Action Compression - Matt Pocock 确定性接缝)
        with tracer.span("CACHE_CHECK", node="PLANNER") as span:
            cached_plan = evaluate_action_cache(user_input, target_prompt_ver="2.0")
            if cached_plan:
                span.set_result("命中经验缓存")
            else:
                span.set_result("未命中缓存")

        if cached_plan:
            # [FIX-TRACE] to_legacy_list 必须在 span 提交后调用：
            # 否则 CACHE_CHECK 事件尚未入列，命中分支的执行轨迹恒为空
            return {
                **cached_plan,
                "execution_trace": tracer.to_legacy_list(),
            }

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
                "messages": []
            }

        # 3. LLM 动态规划路径 [Matt Pocock Deep Module: planner_context_assembler]
        with tracer.span("LLM_PLANNING", node="PLANNER") as span:
            ctx_payload = await assemble_planner_context(state, user_input=user_input)

            # 调用统一 Provider (严格施加预算限制，防止生成 4K 冗余长文)
            response = await llm_provider.chat(
                role=ctx_payload.role,
                messages=ctx_payload.prompt_messages,
                config=config,
                state=state,
                max_tokens=600  # [V220.0 瘦身] 严格限制规划输出预算，阻断对后续 Coder 输入的 4K 污染
            )

            content = str(response.content)

            # 解析响应 [Matt Pocock Deep Module: planner_evaluator]
            methodology, tasks = parse_planner_response(content)
            span.set_result(f"完成路径规划，生成任务 {len(tasks)} 条")

        # [V220.0 Matt Pocock 局部性优化] 向后序 Coder 仅传递精简紧凑的规划决策，彻底阻断上下文滚雪球
        compact_msg = format_compact_plan_message(methodology, tasks)

        return {
            "tasks": tasks[:3],
            "methodology": methodology,
            "messages": [compact_msg],
            "execution_trace": tracer.to_legacy_list()
        }

# 单例导出
planner_agent = AuditPlannerAgent()
