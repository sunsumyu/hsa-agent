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
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
import time

from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from app.core.observability import build_obs_config
from app.core.memory.manager import memory_hub

class LLMProvider:
    def __init__(self):
        self.default_model = "doubao-pro-32k"

    def _bind_llm_options(
        self,
        llm: Any,
        tools: Optional[List[Any]],
        max_tokens_val: Any,
    ) -> Any:
        if tools:
            llm = llm.bind_tools(tools)
        if max_tokens_val:
            llm = llm.bind(max_tokens=int(max_tokens_val))
        return llm

    def _finalize_llm_response(
        self,
        role: str,
        response: Any,
        actual_model_id: str,
        messages: List[BaseMessage],
        session_id: str,
        latency_ms: float,
    ) -> Any:
        self._record_usage(role, response, actual_model_id, messages, latency_ms=latency_ms)
        if hasattr(response, "additional_kwargs"):
            response.additional_kwargs.update({
                "audit_latency_ms": latency_ms,
                "audit_model_id": actual_model_id,
                "audit_role": role,
                "audit_timestamp": time.time(),
            })
        memory_hub.store_working(f"llm:{session_id}", getattr(response, "content", str(response)))
        return response

    async def chat(
        self,
        role: str,
        messages: List[BaseMessage],
        config: Optional[RunnableConfig] = None,
        state: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.0,
        **kwargs,
    ) -> Any:
        """[V168.0] 增强型 Chat 接口：支持 config/kwargs 覆盖、Tier 映射与协议自愈重试。"""
        from app.core.protocol.dialogue_sanitizer import sanitize_dialogue_protocol

        conf = (config or {}).get("configurable", {})
        model_id = conf.get("model_id") or kwargs.get("model_id") or self.default_model
        if model_id in ("HEAVY", "LIGHT"):
            model_id = self._resolve_tier_id(model_id)
        logger.info(f"🤖 [LLMProvider] 正在调用模型: {model_id} (Role: {role})")

        retry_count = state.get("retry_count", 0) if state else 0
        session_id = state.get("session_id", "default") if state else "default"
        llm, actual_model_id = await model_manager.get_llm_by_role(role, retry_count=0, config=config)
        messages = await self._enrich_context_if_needed(role, messages, state)
        llm = self._bind_llm_options(llm, tools, kwargs.get("max_tokens"))
        obs_config = build_obs_config(config, role, state or {})
        messages = sanitize_dialogue_protocol(messages)

        start_time = time.time()
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                chain_desc = ", ".join(
                    f"{getattr(m, 'type', m.__class__.__name__)}(has_tc={bool(getattr(m, 'tool_calls', None))})"
                    for m in messages
                )
                logger.info(f"🐛 [LLM Debug] 消息链结构: {chain_desc}")
                response = await self._execute_model_call(llm, messages, obs_config)
                latency_ms = (time.time() - start_time) * 1000
                return self._finalize_llm_response(role, response, actual_model_id, messages, session_id, latency_ms)
            except Exception as exc:
                logger.error(f"❌ [LLMProvider] 调用失败 ({role} | {actual_model_id}): {exc}")
                if attempt >= max_attempts - 1:
                    logger.error("💥 [LLMProvider] 算力池彻底枯竭或网络瘫痪，放弃重试。")
                    raise exc
                logger.warning(f"🔄 [LLMProvider] 正在尝试重新寻址并重试 (Attempt {attempt + 1}/{max_attempts})...")
                llm, actual_model_id = await model_manager.get_llm_by_role(role, retry_count=retry_count, config=config)
                llm = self._bind_llm_options(llm, tools, None)

    async def _enrich_context_if_needed(
        self, 
        role: str, 
        messages: List[BaseMessage], 
        state: Optional[Dict[str, Any]]
    ) -> List[BaseMessage]:
        """
        [Context Engineering] 运行工业级 GSSC 上下文治理流水线。
        仅针对需要外部事实经验与物理库表结构(DDL)的代码生成与复杂规划角色。
        """
        if role not in ["planner_heavy", "coder"] or not state:
            return messages

        user_input = (
            state.get("current_turn_query") 
            or self._extract_last_user_message(messages) 
            or (state.get("metadata") or {}).get("user_question")
        )
        if not user_input:
            return messages

        from app.infra.endpoint_pool_manager import endpoint_pool_manager
        from app.core.schemas import RoleConfigV2
        from app.core.context.context_builder import ContextBuilder

        role_cfg = endpoint_pool_manager.roles.get(role)
        if not role_cfg:
            role_cfg = RoleConfigV2(pool="tier-1-chat", max_input_tokens=4000, max_output_tokens=2000)

        metadata = dict(state.get("metadata") or {})
        if "target_tables" not in metadata and state.get("target_tables"):
            metadata["target_tables"] = state.get("target_tables")

        builder = ContextBuilder(role_cfg)
        return await builder.build_optimal_context(
            user_query=user_input,
            history=messages,
            metadata=metadata
        )

    async def _execute_model_call(
        self, 
        llm: Any, 
        messages: List[BaseMessage], 
        obs_config: Any
    ) -> AIMessage:
        """
        执行模型物理调用（适配 streaming 与 非流式），并解包 Response Content。
        """
        from app.core.protocol.dialogue_sanitizer import unpack_response_content

        if getattr(llm, "streaming", False):
            chunks = []
            async for chunk in llm.astream(messages, config=obs_config):
                chunks.append(chunk)
            if chunks:
                response = chunks[0]
                for chunk in chunks[1:]:
                    try:
                        response = response + chunk
                    except Exception as exc:
                        logger.debug(f"[LLMProvider] stream chunk merge fallback: {exc}")
                # 严防普通 Message 相加被 LangChain 重载退化为 ChatPromptTemplate
                if not isinstance(response, BaseMessage):
                    combined_content = "".join(str(getattr(c, "content", "") or "") for c in chunks)
                    response = AIMessage(content=combined_content)
            else:
                response = AIMessage(content="")
        else:
            response = await llm.ainvoke(messages, config=obs_config)


        response.content = unpack_response_content(
            response.content,
            has_tool_calls=bool(getattr(response, "tool_calls", None))
        )
        return response


    def _resolve_tier_id(self, tier: str) -> str:
        """将逻辑层级映射为物理模型 ID (从配置中心/环境变量读取)"""
        import os
        if tier == "HEAVY":
            return os.getenv("HEAVY_MODEL", "doubao-pro-32k")
        return os.getenv("LIGHT_MODEL", "doubao-smart") # 默认 Lite 模型

    def _extract_last_user_message(self, messages: List[Union[BaseMessage, tuple]]) -> str:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                return str(msg.content)
            elif isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "human":
                return str(msg[1])
        return ""

    def _record_usage(self, role: str, response: Any, model_id: str, messages: List[Union[BaseMessage, tuple]], latency_ms: float = 0):
        usage = getattr(response, "usage_metadata", {})
        if not usage and hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
        
        in_t = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        out_t = usage.get("output_tokens", usage.get("completion_tokens", 0))
        
        # 防御性提取 Prompt 文本
        prompt_text = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                prompt_text = str(last_msg.content)
            elif isinstance(last_msg, tuple) and len(last_msg) == 2:
                prompt_text = str(last_msg[1])
            else:
                prompt_text = str(last_msg)
        
        usage_tracker.record_usage(
            model_id, 
            in_t, 
            out_t, 
            prompt=prompt_text, 
            response_text=str(getattr(response, "content", "")),
            latency_ms=latency_ms
        )

# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

llm_provider = LazyProxy("llm_provider")
