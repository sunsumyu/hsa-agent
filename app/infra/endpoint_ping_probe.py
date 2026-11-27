"""
Endpoint Ping Probe Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates low-cost ping probe
dispatch, provider credential resolution, and network error containment behind
a clean, focused async interface.
"""
import os
from typing import Any, Optional
from loguru import logger
from langchain_core.messages import HumanMessage


class EndpointPingProbe:
    """端点极简 ping 探针深模块"""

    def __init__(self, factory: Any = None):
        self.factory = factory

    def _resolve_credentials(self, ep: Any):
        if self.factory:
            return self.factory.resolve_credentials(ep)
        from app.infra.llm_factory import LLMFactory
        return LLMFactory().resolve_credentials(ep)

    async def ping_endpoint(self, ep_id: str, ep: Any) -> bool:
        """对单个物理节点发送最廉价的 ping 请求 (max_tokens=1) 以验证可用性"""
        provider = getattr(ep, "provider", "openai")
        api_key, base_url = self._resolve_credentials(ep)

        if not api_key:
            return False

        try:
            if provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(
                    model=ep.model_name,
                    api_key=api_key,
                    google_api_key=api_key,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0,
                )
            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "http://103.236.76.197:11223/anthropic")
                llm = ChatAnthropic(
                    model_name=ep.model_name,
                    anthropic_api_key=api_key,
                    anthropic_api_url=base_url,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0,
                )
            else:
                from langchain_openai import ChatOpenAI
                default_headers = {}
                if provider == "dashscope":
                    default_headers["x-dashscope-sse"] = "enable"

                llm = ChatOpenAI(
                    model=ep.model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0,
                    default_headers=default_headers,
                )

            await llm.ainvoke([HumanMessage(content="ping")], max_tokens=1)
            return True
        except Exception as e:
            logger.debug(f"拨测 {ep_id} 发生异常 (预期中): {e}")
            return False
