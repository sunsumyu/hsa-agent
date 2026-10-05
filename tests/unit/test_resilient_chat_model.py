# tests/unit/test_resilient_chat_model.py
import pytest
import asyncio
from typing import List, Optional
from pydantic import ConfigDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.outputs import ChatResult, ChatGeneration


class MockBaseChatModel(BaseChatModel):
    """用于测试的 Mock 底层 ChatModel"""
    response_text: str = "正常审计回复"
    fail_with_rate_limit: int = 0  # 失败次数
    fail_with_quota_error: bool = False
    fail_with_invalid_param: bool = False
    return_dict_content: bool = False
    call_count: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        self.call_count += 1
        if self.fail_with_invalid_param:
            raise ValueError("InvalidParameter: 消息顺序错误")
        if self.fail_with_quota_error:
            raise ValueError("quota_exceeded: 余额不足")
        if self.fail_with_rate_limit > 0:
            self.fail_with_rate_limit -= 1
            raise ValueError("429 rate limit exceeded")

        content = [{"type": "text", "text": self.response_text}] if self.return_dict_content else self.response_text
        msg = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)


class MockUsageTracker:
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(str(text)) // 4)


class MockEndpointPoolManager:
    def __init__(self):
        self.failed_endpoints = []

    def record_failure(self, ep_id: str, err: str):
        self.failed_endpoints.append((ep_id, err))


@pytest.fixture(autouse=True)
def setup_container():
    from app.core.container import ServiceProvider
    mock_tracker = MockUsageTracker()
    mock_pool = MockEndpointPoolManager()
    ServiceProvider.override("usage_tracker", mock_tracker)
    ServiceProvider.override("endpoint_pool_manager", mock_pool)
    yield
    ServiceProvider.reset()


@pytest.mark.asyncio
async def test_resilient_model_normal_passthrough():
    from app.infra.enriched_llm import ResilientChatModel
    mock = MockBaseChatModel(response_text="查到 10 条分解住院记录")
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-node")

    res = await wrapper.ainvoke([HumanMessage(content="查询违规")])
    assert res.content == "查到 10 条分解住院记录"
    assert getattr(res, "usage_metadata", None) is not None
    assert res.usage_metadata["total_tokens"] > 0


@pytest.mark.asyncio
async def test_resilient_model_anti_chat_guard():
    from app.infra.enriched_llm import ResilientChatModel
    mock = MockBaseChatModel(response_text="你好，我是AI，很高兴为您服务！有什么可以帮您？")
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-chatty-node")

    with pytest.raises(ValueError, match="Chatty response detected"):
        await wrapper.ainvoke([HumanMessage(content="查询违规")])


@pytest.mark.asyncio
async def test_resilient_model_anti_chat_probe_exemption():
    from app.infra.enriched_llm import ResilientChatModel
    mock = MockBaseChatModel(response_text="你好，有什么可以帮您")
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-probe-node")

    # 探活消息 ping 应该被豁免
    res = await wrapper.ainvoke([HumanMessage(content="ping")])
    assert res.content == "你好，有什么可以帮您"


@pytest.mark.asyncio
async def test_resilient_model_rate_limit_retry():
    from app.infra.enriched_llm import ResilientChatModel
    # 模拟第 1 次 429，第 2 次成功
    mock = MockBaseChatModel(response_text="重试成功", fail_with_rate_limit=1)
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-retry-node", backoff_base=0.01)

    res = await wrapper.ainvoke([HumanMessage(content="查询")])
    assert res.content == "重试成功"
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_resilient_model_content_normalization():
    from app.infra.enriched_llm import ResilientChatModel
    mock = MockBaseChatModel(return_dict_content=True, response_text="归一化文本")
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-claude-node")

    res = await wrapper.ainvoke([HumanMessage(content="查询")])
    assert isinstance(res.content, str)
    assert res.content == "归一化文本"


def test_transitional_factory_functions():
    from app.infra.enriched_llm import (
        EnrichedChatOpenAI,
        EnrichedChatGoogleGenerativeAI,
        EnrichedChatAnthropic,
        ResilientChatModel
    )

    # 验证工厂函数返回 ResilientChatModel
    m1 = EnrichedChatOpenAI(model="gpt-4o", api_key="sk-fake", endpoint_id="ep-1")
    assert isinstance(m1, ResilientChatModel)
    assert m1.endpoint_id == "ep-1"

    m2 = EnrichedChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key="fake-key", endpoint_id="ep-2")
    assert isinstance(m2, ResilientChatModel)
    assert m2.endpoint_id == "ep-2"

    m3 = EnrichedChatAnthropic(model_name="claude-3-5-sonnet-20241022", anthropic_api_key="fake-key", endpoint_id="ep-3")
    assert isinstance(m3, ResilientChatModel)
    assert m3.endpoint_id == "ep-3"
