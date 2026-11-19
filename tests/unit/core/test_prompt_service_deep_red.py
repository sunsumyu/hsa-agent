# -*- coding: utf-8 -*-
"""
tests/unit/core/test_prompt_service_deep_red.py
===============================================
[TDD Red -> Green] Prompt 动态治理深模块 (PromptRegistryService) 契约测试
Driven by: Matt Pocock Deep Module Principles

测试项：
1. 注册于 ServiceProvider DI 容器
2. 最小接口契约：get_prompt 统一处理本地 Fallback 与云端拉取
3. 本地内存 TTL 缓存隔离 (避免重复网络 IO)
4. 云端拉取失败时 100% 优雅降级本地模板，主链路永不抛异常
"""

from unittest.mock import MagicMock
import pytest
from langchain_core.prompts import ChatPromptTemplate
from app.core.container import ServiceProvider
from app.core.bootstrap import register_services


@pytest.fixture(autouse=True)
def clean_di():
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def test_prompt_registry_registered_in_di():
    """断言 1: Prompt 治理服务受管注册于 DI 容器"""
    reg = ServiceProvider.resolve("prompt_registry")
    assert reg is not None
    assert reg.__class__.__name__ == "PromptRegistryService"


def test_prompt_registry_local_fallback():
    """断言 2: 无云端句柄时直接使用本地 fallback 模板 (支持 str 与 ChatPromptTemplate 双态)"""
    reg = ServiceProvider.resolve("prompt_registry")

    raw_tpl = "你是一个专业的医保审计专家，目标问题: {question}"
    prompt_obj = reg.get_prompt("audit_planner", fallback_template=raw_tpl)

    assert isinstance(prompt_obj, ChatPromptTemplate)
    formatted = prompt_obj.format(question="保妇康栓排查")
    assert "保妇康栓排查" in formatted

    # 测试直接传入现有 ChatPromptTemplate 对象作为 fallback
    direct_tpl = ChatPromptTemplate.from_template("预构模板: {var}")
    prompt_obj_direct = reg.get_prompt("direct_tpl", fallback_template=direct_tpl)
    assert prompt_obj_direct is direct_tpl


def test_prompt_registry_caching():
    """断言 3: 高频连续调用命中内存缓存 (返回同一对象指针)"""
    reg = ServiceProvider.resolve("prompt_registry")

    raw_tpl = "审计模板: {text}"
    p1 = reg.get_prompt("cached_prompt", fallback_template=raw_tpl)
    p2 = reg.get_prompt("cached_prompt", fallback_template=raw_tpl)

    assert p1 is p2, "在 TTL 周期内必须命中内存缓存，杜绝重复解析/拉取"


def test_prompt_registry_hub_pull_and_graceful_fallback():
    """断言 4: 云端网络异常时自动无缝降级到本地 fallback，绝不让上层业务崩溃"""
    reg = ServiceProvider.resolve("prompt_registry")

    # 模拟云端客户端抛出网络超时异常
    mock_obs = MagicMock()
    mock_client = MagicMock()
    mock_client.pull_prompt.side_effect = ConnectionError("Cloud hub timeout")
    mock_obs._langsmith_client = mock_client
    ServiceProvider.override("observability", mock_obs)

    fallback = "本地紧急兜底指令: {query}"
    # 尽管 hub 报错，get_prompt 绝不可崩溃，必须平滑返回 fallback 模板
    safe_prompt = reg.get_prompt(
        "failing_prompt",
        fallback_template=fallback,
        hub_handle="argus/broken-hub-repo:prod"
    )

    assert isinstance(safe_prompt, ChatPromptTemplate)
    formatted = safe_prompt.format(query="查询异常")
    assert "本地紧急兜底指令: 查询异常" in formatted
