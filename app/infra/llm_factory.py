"""
app/infra/llm_factory.py
========================
[V142.0 / Matt Pocock Deep Module] 增强型 LLM 实例构建工厂
封装凭证打捞（专属环境变量与通用环境变量回退）、共享连接池注入，
以及 Google / Anthropic / DashScope / OpenAI 多协议客户端实例化。
"""

import os
import re
from typing import Optional, Tuple, Any, Dict
from loguru import logger
import httpx

from app.core.schemas import ModelConfig
from app.infra.enriched_llm import (
    EnrichedChatOpenAI,
    EnrichedChatGoogleGenerativeAI,
    EnrichedChatAnthropic,
)


class LLMFactory:
    """多模型提供者客户端构造工厂深模块"""

    def __init__(self):
        self._async_client: Optional[httpx.AsyncClient] = None

    @property
    def async_client(self) -> httpx.AsyncClient:
        """全局共享异步 HTTP 客户端：解决 Event loop is closed 报错并复用长连接池"""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._async_client

    def resolve_credentials(self, cfg: Any) -> Tuple[Optional[str], Optional[str]]:
        """
        智能凭证解析：支持特定环境变量与通用环境变量的层级打捞。
        Returns: (api_key, base_url)
        """
        api_key_env = getattr(cfg, "api_key_env", None)
        base_url_env = getattr(cfg, "base_url_env", None)

        # 1. 优先尝试特定环境变量
        api_key = os.getenv(api_key_env) if api_key_env else None
        base_url = os.getenv(base_url_env) if base_url_env else None

        # 2. 如果缺失，尝试通用环境变量 LLM_API_KEY / LLM_BASE_URL
        if not api_key:
            api_key = os.getenv("LLM_API_KEY")
            if api_key:
                logger.info(f"💡 [SmartDiscovery] 节点 {getattr(cfg, 'model_name', 'unknown')} 已通过通用密钥 LLM_API_KEY 激活")

        if not base_url and os.getenv("LLM_BASE_URL"):
            base_url = os.getenv("LLM_BASE_URL")
            logger.info(f"💡 [SmartDiscovery] 节点 {getattr(cfg, 'model_name', 'unknown')} 已通过通用地址 LLM_BASE_URL 激活")

        return api_key, base_url

    def create_llm(self, name: str, cfg: Any) -> Optional[Any]:
        """根据配置和提供者构造 EnrichedChat 实例"""
        provider = getattr(cfg, "provider", "openai")
        api_key, base_url = self.resolve_credentials(cfg)
        model_name = getattr(cfg, "model_name", name)
        temperature = getattr(cfg, "temperature", 0.3)

        if not api_key:
            logger.warning(f"模型 {name} 缺少 API_KEY，跳过。")
            return None

        default_headers: Dict[str, str] = {}
        if provider == "dashscope":
            default_headers["x-dashscope-sse"] = "enable"

        try:
            if provider == "google":
                return EnrichedChatGoogleGenerativeAI(
                    model=model_name,
                    api_key=api_key,
                    google_api_key=api_key,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    endpoint_id=name,
                )
            elif provider == "anthropic":
                base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "http://103.236.76.197:11223/anthropic")
                clean_anthropic_url = re.sub(r"/v1/messages/?$", "", base_url) if base_url else base_url
                max_tokens = getattr(cfg, "max_tokens", 8192)
                model_kwargs = {}
                if getattr(cfg, "disable_thinking", False):
                    model_kwargs["thinking"] = {"type": "disabled"}
                return EnrichedChatAnthropic(
                    model_name=model_name,
                    anthropic_api_key=api_key,
                    anthropic_api_url=clean_anthropic_url,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model_kwargs=model_kwargs,
                    timeout=120.0,
                    streaming=True,
                    endpoint_id=name,
                )
            else:
                return EnrichedChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    default_headers=default_headers,
                    http_async_client=self.async_client,
                    endpoint_id=name,
                )
        except Exception as e:
            logger.error(f"LLM 实例化失败: {name} | {e}")
            return None
