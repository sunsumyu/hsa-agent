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
from app.memory.semantic_memory import cognitive_memory_manager

class LLMProvider:
    def __init__(self):
        self.default_model = "doubao-pro-32k"

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

        # 1. 获取 LLM 实例与实际模型 ID (初始寻址使用 retry_count=0 保证首选端点绑定有效)
        llm, actual_model_id = await model_manager.get_llm_by_role(
            role, 
            retry_count=0, 
            config=config
        )

        # 2. 运行工业级 GSSC 上下文治理流水线 (Context Engineering)
        messages = await self._enrich_context_if_needed(role, messages, state)

        # 3. 动态参数与工具绑定 (锁定输出预算，严防长篇累牍与 Token 膨胀)
        if tools:
            llm = llm.bind_tools(tools)
        max_tokens_val = kwargs.get("max_tokens")
        if max_tokens_val:
            llm = llm.bind(max_tokens=int(max_tokens_val))

        # 4. 构建可观测性配置
        obs_config = build_obs_config(config, role, state or {})
        
        # 5. [Protocol Guard] 协议防御与归一化 (深模块收口工具配对、多 System 归一、角色交替折叠、用户消息兜底)
        from app.core.protocol.dialogue_sanitizer import sanitize_dialogue_protocol
        messages = sanitize_dialogue_protocol(messages)

        # 6. 执行调用与重试
        start_time = time.time()
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                # 打印消息链结构，抓取 pairing 漏洞
                logger.info(f"🐛 [LLM Debug] 消息链结构: " + ", ".join(f"{getattr(m, 'type', m.__class__.__name__)}(has_tc={bool(getattr(m, 'tool_calls', None))})" for m in messages))
                
                response = await self._execute_model_call(llm, messages, obs_config)
                
                latency_ms = (time.time() - start_time) * 1000
                
                # 7. 计费与用量追踪
                self._record_usage(role, response, actual_model_id, messages, latency_ms=latency_ms)
                
                # 8. 注入审计元数据 (Audit Metadata Injection)
                if hasattr(response, "additional_kwargs"):
                    response.additional_kwargs.update({
                        "audit_latency_ms": latency_ms,
                        "audit_model_id": actual_model_id,
                        "audit_role": role,
                        "audit_timestamp": time.time()
                    })
                
                # 9. 更新认知记忆
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
                    except Exception:
                        pass
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
