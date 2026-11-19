# -*- coding: utf-8 -*-
"""
app/core/prompt_service.py
==========================
[Matt Pocock Deep Module] 统一 Prompt 治理服务 (PromptRegistryService)
对外部呈现极小接口（get_prompt, clear_cache），对内吞噬：
- LangSmith Hub 动态拉取与解析
- 60 秒本地内存 TTL 高速缓存（防止重复外网请求）
- 云端网络抖动/超时/未连通时的 100% 本地平滑降级 (Zero Crash Guarantee)
"""

import time
from typing import Dict, Any, Optional, Tuple, Union
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from app.core.container import ServiceProvider


class PromptRegistryService:
    """Prompt 注册与动态拉取深模块服务"""

    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache_ttl_seconds = cache_ttl_seconds
        # 内部缓存结构: {prompt_name: (timestamp, ChatPromptTemplate)}
        self._cache: Dict[str, Tuple[float, ChatPromptTemplate]] = {}

    def get_prompt(
        self,
        prompt_name: str,
        fallback_template: Union[str, ChatPromptTemplate],
        hub_handle: Optional[str] = None
    ) -> ChatPromptTemplate:
        """
        [极窄接口] 获取 Prompt 模板对象
        支持传入字符串模板或已有 ChatPromptTemplate 实例作为 fallback。
        优先读取内存缓存，次选 LangSmith Hub，失败则 100% 平滑回退到 fallback_template
        """
        now = time.time()

        # 1. 内存高速缓存命中
        if prompt_name in self._cache:
            cache_t, cached_obj = self._cache[prompt_name]
            if now - cache_t < self.cache_ttl_seconds:
                return cached_obj

        # 2. 尝试从 LangSmith Hub 拉取
        if hub_handle:
            obs = ServiceProvider.try_resolve("observability")
            client = getattr(obs, "_langsmith_client", None) if obs else None
            if client:
                try:
                    logger.debug(f"[PromptRegistry] 正在从 Hub 同步: {hub_handle}")
                    prompt_obj = client.pull_prompt(hub_handle)
                    if isinstance(prompt_obj, ChatPromptTemplate):
                        self._cache[prompt_name] = (now, prompt_obj)
                        logger.info(f"✨ [PromptRegistry] 云端 Prompt 同步成功: {hub_handle}")
                        return prompt_obj
                except Exception as e:
                    logger.warning(f"⚠️ [PromptRegistry] 云端 Prompt ({hub_handle}) 拉取失败，自动平滑降级: {e}")

        # 3. 兜底解析本地模板
        if isinstance(fallback_template, ChatPromptTemplate):
            fallback_obj = fallback_template
        else:
            fallback_obj = ChatPromptTemplate.from_template(str(fallback_template))

        self._cache[prompt_name] = (now, fallback_obj)
        return fallback_obj

    def clear_cache(self, prompt_name: Optional[str] = None) -> None:
        """清理指定或全量内存 Prompt 缓存"""
        if prompt_name:
            self._cache.pop(prompt_name, None)
        else:
            self._cache.clear()
