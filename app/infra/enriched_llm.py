"""
app/infra/enriched_llm.py
=========================
[Phase 3.3] Enriched LLM wrappers and reranker.

Extracted from model_manager.py. These classes add fault-awareness (anti-chat
guard, rate-limit retry, token estimation) to ChatOpenAI and ChatGoogleGenerativeAI.
"""

import os
import asyncio
import time
import requests
from loguru import logger
from typing import Dict, List, Any
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.runnables import RunnableBinding
from typing import Dict, List, Any, Optional, Sequence, Union, Callable

from app.infra.usage_tracker import usage_tracker
from app.infra.endpoint_pool_manager import endpoint_pool_manager
from app.core.schemas import ModelConfig


from pydantic import ConfigDict

class ResilientChatModel(BaseChatModel):
    """
    [Phase 1] 统一韧性模型装饰器：
    消除供应商子类继承，通过组合代理原生 BaseChatModel，
    集中处理：Anti-Chat 拦截、Claude 结构化内容归一化、Token 用量估算补全、429 指数退避重试与切流上报。
    """
    inner_model: Any
    endpoint_id: str = "unknown"
    max_retries: int = 2
    backoff_base: float = 2.0  # 重试退避基数 (秒)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return f"resilient-{getattr(self.inner_model, '_llm_type', 'unknown')}"

    @property
    def streaming(self) -> bool:
        return getattr(self.inner_model, "streaming", False)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        if hasattr(self.inner_model, "bind_tools"):
            bound_inner = self.inner_model.bind_tools(tools, **kwargs)
            return ResilientChatModel(
                inner_model=bound_inner,
                endpoint_id=self.endpoint_id,
                max_retries=self.max_retries,
                backoff_base=self.backoff_base
            )
        return super().bind_tools(tools, **kwargs)

    def _enrich_result(self, result: ChatResult, messages: List[BaseMessage]) -> None:
        """强化结果：Anti-Chat 闲聊检测、Claude 内容扁平化与 Token 估算"""
        _is_probe = (
            len(messages) == 1
            and hasattr(messages[0], "content")
            and str(messages[0].content).strip().lower() in ("ping", "1", "hi", "test")
        )

        for gen in result.generations:
            msg = gen.message
            # 1. Claude/Thinking 内容归一化与思维链沉淀
            if isinstance(msg.content, list):
                text_parts = []
                thinking_parts = []
                for item in msg.content:
                    if isinstance(item, str):
                        if item: text_parts.append(item)
                    elif isinstance(item, dict):
                        if item.get("type") == "text" and item.get("text"):
                            text_parts.append(item["text"])
                        elif "text" in item and item["text"]:
                            text_parts.append(item["text"])
                        elif item.get("type") == "thinking" and item.get("thinking"):
                            thinking_parts.append(item["thinking"])

                # 沉淀思维链至 additional_kwargs 供可观测链路与审计追溯
                if thinking_parts and not msg.additional_kwargs.get("thinking"):
                    msg.additional_kwargs["thinking"] = "\n".join(thinking_parts)

                if text_parts or not getattr(msg, "tool_calls", None):
                    msg.content = "\n".join(text_parts).strip()

            # 2. 空内容与思维链溢出截断门禁 (Thinking Overflow & Empty-Content Guard)
            stop_reason = (
                getattr(msg, "response_metadata", {}).get("stop_reason")
                or (gen.generation_info or {}).get("stop_reason")
            )
            content_str = str(msg.content).strip()
            if not content_str and not getattr(msg, "tool_calls", None) and not _is_probe:
                if stop_reason == "max_tokens":
                    logger.warning(f"🚫 [THINKING_OVERFLOW] 节点 {self.endpoint_id} 思考链耗尽 max_tokens 导致正文截断为空，强行切流。")
                    endpoint_pool_manager.record_failure(self.endpoint_id, "Thinking overflow: empty content due to max_tokens.")
                    raise ValueError(f"Thinking overflow truncated empty content from {self.endpoint_id}")
                else:
                    logger.warning(f"🚫 [EMPTY_OUTPUT] 节点 {self.endpoint_id} 返回空消息体，触发自动熔断切流。")
                    endpoint_pool_manager.record_failure(self.endpoint_id, "Empty message content returned.")
                    raise ValueError(f"Empty message content returned from {self.endpoint_id}")

            # 3. Anti-Chat Guard: 过滤无意义闲聊废话
            content_str = str(msg.content)
            chatty_keywords = ["你好", "很高兴为您服务", "我是一个大语言模型", "作为一个AI", "有什么可以帮您", "抱歉"]
            if not _is_probe and any(kw in content_str for kw in chatty_keywords) and len(content_str) < 300:
                logger.warning(f"🚫 [ANTI_CHAT] 节点 {self.endpoint_id} 输出了闲聊废话，强行切流。")
                endpoint_pool_manager.record_failure(self.endpoint_id, "Detected conversational chatty response.")
                raise ValueError(f"Chatty response detected from {self.endpoint_id}")

            # 3. 财务级 Token 估算补全
            if not getattr(msg, "usage_metadata", None) or msg.usage_metadata.get("total_tokens", 0) == 0:
                prompt_text = "".join([str(m.content) for m in messages if hasattr(m, "content")])
                in_t = usage_tracker._estimate_tokens(prompt_text)
                out_t = usage_tracker._estimate_tokens(content_str)
                msg.usage_metadata = {
                    "input_tokens": in_t,
                    "output_tokens": out_t,
                    "total_tokens": in_t + out_t
                }

    def _resolve_inner(self, kwargs: Dict[str, Any]):
        """
        bind_tools() 返回的是 RunnableBinding(bound=原生模型, kwargs={"tools": ...})。
        RunnableBinding 会把 `_agenerate/_generate` 属性透传给原生模型，若直接调用会静默
        丢掉绑定的 tools 等参数，因此这里拆包并合并 kwargs (调用方显式传入的优先)。
        """
        inner = self.inner_model
        merged = dict(kwargs)
        while isinstance(inner, RunnableBinding):
            merged = {**inner.kwargs, **merged}
            inner = inner.bound
        return inner, merged

    def _should_ignore_breaker(self, err_msg: str) -> bool:
        """400 InvalidParameter 等请求级错误不熔断节点"""
        return "InvalidParameter" in err_msg or "Invalid messages" in err_msg

    async def _agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs
    ) -> ChatResult:
        attempt = 0
        inner, kwargs = self._resolve_inner(kwargs)
        while True:
            try:
                if hasattr(inner, "_agenerate"):
                    result = await inner._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
                else:
                    res_msg = await inner.ainvoke(messages, stop=stop, **kwargs)
                    result = ChatResult(generations=[ChatGeneration(message=res_msg)])
                self._enrich_result(result, messages)
                return result
            except Exception as e:
                err_msg = str(e)
                if self._should_ignore_breaker(err_msg):
                    logger.warning(f"⚠️ [REQUEST_BUG] 节点 {self.endpoint_id} 返回 400 参数错误 (不熔断): {err_msg[:200]}")
                    raise e

                # 429 限速指数退避重试
                if ("429" in err_msg or "limit" in err_msg.lower()) and attempt < self.max_retries:
                    attempt += 1
                    wait_time = attempt * self.backoff_base
                    logger.warning(f"⏳ [RateLimit-Retry] 节点 {self.endpoint_id} 触发限速，等待 {wait_time}s 后重试 (第 {attempt} 次)...")
                    await asyncio.sleep(wait_time)
                    continue

                # 严重故障或配额耗尽切流
                endpoint_pool_manager.record_failure(self.endpoint_id, err_msg)
                raise e

    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs
    ) -> ChatResult:
        attempt = 0
        inner, kwargs = self._resolve_inner(kwargs)
        while True:
            try:
                if hasattr(inner, "_generate"):
                    result = inner._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
                else:
                    res_msg = inner.invoke(messages, stop=stop, **kwargs)
                    result = ChatResult(generations=[ChatGeneration(message=res_msg)])
                self._enrich_result(result, messages)
                return result
            except Exception as e:
                err_msg = str(e)
                if self._should_ignore_breaker(err_msg):
                    raise e

                if ("429" in err_msg or "limit" in err_msg.lower()) and attempt < self.max_retries:
                    attempt += 1
                    import time
                    wait_time = attempt * self.backoff_base
                    time.sleep(wait_time)
                    continue

                endpoint_pool_manager.record_failure(self.endpoint_id, err_msg)
                raise e


def EnrichedChatOpenAI(**kwargs) -> ResilientChatModel:
    """[Phase 1] 向后兼容工厂函数：包装原生 ChatOpenAI"""
    endpoint_id = kwargs.pop("endpoint_id", "unknown")
    raw_model = ChatOpenAI(**kwargs)
    return ResilientChatModel(inner_model=raw_model, endpoint_id=endpoint_id)


def EnrichedChatGoogleGenerativeAI(**kwargs) -> ResilientChatModel:
    """[Phase 1] 向后兼容工厂函数：包装原生 ChatGoogleGenerativeAI"""
    endpoint_id = kwargs.pop("endpoint_id", "unknown")
    raw_model = ChatGoogleGenerativeAI(**kwargs)
    return ResilientChatModel(inner_model=raw_model, endpoint_id=endpoint_id)


def EnrichedChatAnthropic(**kwargs) -> ResilientChatModel:
    """[Phase 1] 向后兼容工厂函数：包装原生 ChatAnthropic"""
    endpoint_id = kwargs.pop("endpoint_id", "unknown")
    raw_model = ChatAnthropic(**kwargs)
    return ResilientChatModel(inner_model=raw_model, endpoint_id=endpoint_id)


class Reranker:
    """[V44.0] 物理重排序算子：支持火山引擎 Rerank 接口"""
    def __init__(self, name: str, cfg: ModelConfig):
        self.name = name
        self.cfg = cfg
        self.api_key = os.getenv(cfg.api_key_env)
        self.base_url = os.getenv(cfg.base_url_env, "https://ark.cn-beijing.volces.com/api/v3")

    @traceable(name="reranker", run_type="retriever")
    def rerank(self, query: str, documents: List[str], top_n: int = 3) -> List[Dict]:
        if not documents: return []
        
        if self.cfg.provider == "volcengine":
            url = f"{self.base_url}/rerank"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"model": self.cfg.model_name, "query": query, "documents": documents, "top_n": top_n}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    usage_tracker.record_success(self.name)
                    return resp.json().get("results", [])
            except Exception as e:
                logger.error(f"Volc Rerank 异常: {e}")
                usage_tracker.record_failure(self.name, str(e))

        elif self.cfg.provider == "dashscope":
            url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-DashScope-ApiKey": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.cfg.model_name,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_n}
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    usage_tracker.record_success(self.name)
                    return resp.json().get("output", {}).get("results", [])
            except Exception as e:
                logger.error(f"DashScope Rerank 异常: {e}")
                usage_tracker.record_failure(self.name, str(e))
        
        return [{"index": i, "relevance_score": 1.0 - (i * 0.1)} for i in range(min(len(documents), top_n))]
