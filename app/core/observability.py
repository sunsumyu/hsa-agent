"""
app/core/observability.py
=========================
[向后兼容适配层] 为既有模块保持函数签名不变，内部全量委托至 ServiceProvider DI 容器。
遵循 Matt Pocock 的渐进迁移法则 (Non-intrusive Backward-Compatible Aliasing)。
"""

import os
from typing import List, Any, Optional
from langchain_core.runnables import RunnableConfig
from app.core.container import ServiceProvider


def _ensure_bootstrap():
    """保证单机脚本或离线测试在直接调用老函数时，DI 容器已自动装配"""
    if "observability" not in ServiceProvider._factories and "observability" not in ServiceProvider._instances:
        from app.core.bootstrap import register_services
        register_services()


def init_observability():
    """向后兼容：触发 DI 容器懒加载实例化"""
    _ensure_bootstrap()
    return ServiceProvider.resolve("observability")


def shutdown_observability():
    """向后兼容：触发单例安全离场"""
    obs = ServiceProvider.try_resolve("observability")
    if obs and hasattr(obs, "shutdown"):
        obs.shutdown()


def get_callbacks(tags: Optional[List[str]] = None) -> List[Any]:
    """向后兼容：委托至深模块的 get_stream_callbacks()"""
    _ensure_bootstrap()
    obs = ServiceProvider.resolve("observability")
    if hasattr(obs, "get_stream_callbacks"):
        return obs.get_stream_callbacks()
    return []


def get_langsmith_client():
    """向后兼容：建议业务层迁移至 record_feedback() 接口"""
    _ensure_bootstrap()
    obs = ServiceProvider.resolve("observability")
    return getattr(obs, "_langsmith_client", None)


def build_obs_config(config: Optional[RunnableConfig], node_name: str, state: dict) -> RunnableConfig:
    """向后兼容：委托至深模块的 configure_run()"""
    _ensure_bootstrap()
    obs = ServiceProvider.resolve("observability")
    s_id = state.get("session_id", "default")

    feedback = state.get("audit_feedback")
    extra_meta = {
        "retry_count": state.get("retry_count", 0),
        "audit_decision": getattr(feedback, "decision", "N/A") if feedback else "N/A"
    }

    if hasattr(obs, "configure_run"):
        return obs.configure_run(
            node_name=node_name,
            session_id=s_id,
            extra_meta=extra_meta,
            base_config=config
        )

    # 兜底
    cfg = (config or {}).copy()
    cfg.setdefault("callbacks", get_callbacks())
    cfg.setdefault("metadata", {})
    cfg["metadata"].update({"node": node_name, "session_id": s_id, **extra_meta})
    return cfg


def get_langfuse_prompt(prompt_name: str, fallback: Any) -> Any:
    """云端 Prompt 托管助手：优先从云端拉取，物理失败则回退本地"""
    obs = ServiceProvider.try_resolve("observability")
    client = getattr(obs, "_langfuse_client", None) if obs else None
    if not client:
        return fallback

    try:
        prompt = client.get_prompt(prompt_name, cache_ttl_seconds=60)
        from langchain_core.prompts import ChatPromptTemplate
        return ChatPromptTemplate.from_messages([
            ("system", prompt.prompt),
        ])
    except Exception:
        return fallback
