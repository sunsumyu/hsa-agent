"""
Local Service Detector Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates socket probing for
local LLM runtimes (Ollama, vLLM) and automatic model config provisioning.
"""
import os
import socket
from urllib.parse import urlparse
from typing import Dict, Any
from loguru import logger
from app.core.schemas import ModelConfig


class LocalServiceDetector:
    """零配置本地模型服务探测与自动并网注册深模块"""

    _DEFAULT_CHECKS = [
        ("ollama", "http://localhost:11434/v1", "OLLAMA_API_KEY"),
        ("vllm", "http://localhost:8000/v1", "VLLM_API_KEY"),
    ]

    @classmethod
    def discover_local_services(cls, existing_providers: Dict[str, Any]) -> Dict[str, ModelConfig]:
        """探测本地服务并补充到 provider 字典中"""
        new_providers = dict(existing_providers)

        for name, url, key_env in cls._DEFAULT_CHECKS:
            try:
                parsed = urlparse(url)
                with socket.create_connection((parsed.hostname, parsed.port), timeout=0.5):
                    if name not in new_providers:
                        logger.success(f"🚀 [AutoDetect] 发现本地 {name} 服务在 {url} 运行，已自动并网。")
                        new_providers[name] = ModelConfig(
                            provider="openai",
                            model_name=os.getenv("LLM_MODEL_ID", "llama3"),
                            priority=5,
                            tools_support=True,
                            api_key_env=key_env,
                            base_url_env=f"LOCAL_{name.upper()}_URL",
                            daily_quota=999999,
                        )
                        os.environ[f"LOCAL_{name.upper()}_URL"] = url
                        if not os.getenv(key_env):
                            os.environ[key_env] = "sk-local-not-needed"
            except Exception as exc:
                logger.debug(f"[LocalServiceDetector] Local runtime {name} ({url}) not reachable: {exc}")

        return new_providers
