"""
app/core/llm_provider.py
========================
[V150.0] 工业级模型供应层 (Unified LLM Provider)

负责：
1. 统一接口：封装不同角色的 LLM 调用逻辑。
2. 自动中间件：内置计费追踪 (UsageTracker)、可观测性 (Langfuse) 和自愈重试。
3. 提示词增强：自动从 CognitiveMemory 注入历史经验上下文。
"""

from typing import Dict, Any, List, Optional, Union
from loguru import logger
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
import time

from app.model_manager import model_manager
from app.usage_tracker import usage_tracker
from app.observability import build_obs_config
from app.semantic_memory import cognitive_memory_manager

class LLMProvider:
    def __init__(self):
        self.default_model = "deepseek-v3"

    async def chat(
        self, 
        role: str, 
        messages: List[BaseMessage], 
        config: Optional[RunnableConfig] = None,
        state: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.0,
        **kwargs
    ) -> Any:
        """
        [V168.0] 增强型 Chat 接口：
        1. 优先使用 config 里的 model_id (手动覆盖)
        2. 其次使用 kwargs 里的 model_id
        3. 如果是逻辑 Tier (HEAVY/LIGHT)，自动映射物理 ID
        """
        conf = (config or {}).get("configurable", {})
        # 优先级：Config手动指定 > 参数传入 > 默认
        model_id = conf.get("model_id") or kwargs.get("model_id") or self.default_model
        
        # 处理逻辑 Tier 映射
        if model_id in ["HEAVY", "LIGHT"]:
            model_id = self._resolve_tier_id(model_id)
            
        logger.info(f"🤖 [LLMProvider] 正在调用模型: {model_id} (Role: {role})")

        retry_count = state.get("retry_count", 0) if state else 0
        session_id = state.get("session_id", "default") if state else "default"

        # 1. 获取 LLM 实例与实际模型 ID
        llm, actual_model_id = await model_manager.get_llm_by_role(
            role, 
            retry_count=retry_count, 
            config=config
        )

        # 2. 运行工业级 GSSC 上下文治理流水线 (Context Engineering)
        # 仅针对需要大量外部事实经验与结构表结构的核心审计角色
        if role in ["planner_heavy", "coder", "reporter"] and state:
            user_input = self._extract_last_user_message(messages)
            if user_input:
                from app.endpoint_pool_manager import endpoint_pool_manager
                from app.schemas import RoleConfigV2
                from app.core.context_builder import ContextBuilder
                
                # 获取或初始化角色预算配置
                role_cfg = endpoint_pool_manager.roles.get(role)
                if not role_cfg:
                    role_cfg = RoleConfigV2(pool="tier-1-chat", max_input_tokens=4000, max_output_tokens=2000)
                
                # 构建元数据
                target_tables = state.get("target_tables", [])
                metadata = {"target_tables": target_tables}
                
                # 动态生成黄金上下文事实层消息流 (并完成 Gather -> Select -> Structure -> Compress)
                builder = ContextBuilder(role_cfg)
                messages = await builder.build_optimal_context(
                    user_query=user_input,
                    history=messages,
                    metadata=metadata
                )

        # 3. 绑定工具
        if tools:
            llm = llm.bind_tools(tools)

        # 4. 构建可观测性配置
        obs_config = build_obs_config(config, role, state or {})

        # 5. 执行调用
        start_time = time.time()
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                response = await llm.ainvoke(messages, config=obs_config)
                latency_ms = (time.time() - start_time) * 1000
                
                # 6. 计费与用量追踪
                self._record_usage(role, response, actual_model_id, messages, latency_ms=latency_ms)
                
                # 7. 注入审计元数据 (Audit Metadata Injection)
                if hasattr(response, "additional_kwargs"):
                    response.additional_kwargs.update({
                        "audit_latency_ms": latency_ms,
                        "audit_model_id": actual_model_id,
                        "audit_role": role,
                        "audit_timestamp": time.time()
                    })
                
                # 8. 更新认知记忆
                cognitive_memory_manager.add_message(session_id, response)
                
                return response
                
            except Exception as e:
                logger.error(f"❌ [LLMProvider] 调用失败 ({role} | {actual_model_id}): {e}")
                if attempt < max_attempts - 1:
                    logger.warning(f"🔄 [LLMProvider] 正在尝试重新寻址并重试 (Attempt {attempt + 1}/{max_attempts})...")
                    # 因为坏节点已经在底层被 record_failure 熔断，这里再拿一次必将返回备用节点（例如百炼）
                    llm, actual_model_id = await model_manager.get_llm_by_role(role, retry_count=retry_count, config=config)
                    if tools:
                        llm = llm.bind_tools(tools)
                    continue
                else:
                    logger.error("💥 [LLMProvider] 算力池彻底枯竭或网络瘫痪，放弃重试。")
                    raise e

    def _resolve_tier_id(self, tier: str) -> str:
        """将逻辑层级映射为物理模型 ID (从配置中心读取)"""
        from app.core.config import settings
        if tier == "HEAVY":
            return settings.get("HEAVY_MODEL", "deepseek-v3")
        return settings.get("LIGHT_MODEL", "deepseek-v2.5") # 默认 Lite 模型

    def _extract_last_user_message(self, messages: List[BaseMessage]) -> str:
        for msg in reversed(messages):
            if msg.type == "human":
                return str(msg.content)
        return ""

    def _record_usage(self, role: str, response: Any, model_id: str, messages: List[BaseMessage], latency_ms: float = 0):
        usage = getattr(response, "usage_metadata", {})
        if not usage and hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
        
        in_t = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        out_t = usage.get("output_tokens", usage.get("completion_tokens", 0))
        
        usage_tracker.record_usage(
            model_id, 
            in_t, 
            out_t, 
            prompt=str(messages[-1].content) if messages else "", 
            response_text=str(getattr(response, "content", "")),
            latency_ms=latency_ms
        )

# 单例导出
llm_provider = LLMProvider()
