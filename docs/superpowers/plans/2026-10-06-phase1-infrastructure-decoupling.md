# Phase 1: 基础设施解耦 (ResilientChatModel 统一装饰器) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以组合（Decorator Pattern）取代 `enriched_llm.py` 对外部 LangChain 供应商子类的直接派生继承，消除重复代码、Pydantic 属性黑客写法以及异步阻塞混用隐患，实现 100% 向后兼容。

**Architecture:** 定义统一的 `ResilientChatModel(BaseChatModel)` 装饰器，内部通过代理持有原生的 `inner_model: BaseChatModel`，集中负责 Anti-Chat 闲聊拦截、Claude 结构化文本归一化、财务级 Token 缺失估算补全、429 指数退避重试与熔断切流。原有的 `EnrichedChatOpenAI` 等类转化为向后兼容的轻量工厂函数，并在 `model_manager.py` 中移除 `object.__setattr__` 黑客补丁。

**Tech Stack:** Python 3.11, LangChain (`BaseChatModel`, `AIMessage`, `ChatResult`, `ChatGeneration`), Pydantic, pytest, pytest-asyncio, loguru.

## Global Constraints

- **Python 版本**：Python 3.11+
- **无外部依赖破坏**：必须保持与现有 LangChain Runnable 体系（`.bind_tools()`, `.with_fallbacks()`）无缝兼容。
- **向后兼容**：`app/infra/enriched_llm.py` 必须继续导出 `EnrichedChatOpenAI`、`EnrichedChatGoogleGenerativeAI`、`EnrichedChatAnthropic`、`Reranker`，保证外部导入零修改。
- **异步安全**：在异步执行流（`_agenerate`）中严禁使用任何同步 `time.sleep`，统一使用 `await asyncio.sleep`。
- **测试环境执行**：测试命令统一使用 `python -m pytest <path> -v`。

---

### Task 1: 编写 `ResilientChatModel` 统一装饰器与核心治理管道

**Files:**
- Create: `tests/unit/test_resilient_chat_model.py`
- Modify: `app/infra/enriched_llm.py:20-260`

**Interfaces:**
- Consumes: `langchain_core.language_models.chat_models.BaseChatModel`, `app.infra.usage_tracker.usage_tracker`, `app.infra.endpoint_pool_manager.endpoint_pool_manager`
- Produces: `ResilientChatModel(BaseChatModel)`
  - Attributes: `inner_model: BaseChatModel`, `endpoint_id: str`, `max_retries: int`
  - Methods: `_generate(messages, stop=None, run_manager=None, **kwargs) -> ChatResult`, `_agenerate(messages, stop=None, run_manager=None, **kwargs) -> ChatResult`

- [ ] **Step 1: Write the failing tests for ResilientChatModel**

```python
# tests/unit/test_resilient_chat_model.py
import pytest
import asyncio
from typing import List, Optional
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


@pytest.mark.asyncio
async def test_resilient_model_normal_passthrough():
    from app.infra.enriched_llm import ResilientChatModel
    mock = MockBaseChatModel(response_text="查到 10 条分解住院记录")
    wrapper = ResilientChatModel(inner_model=mock, endpoint_id="test-node")

    res = await wrapper.ainvoke([HumanMessage(content="查询违规")])
    assert res.content == "查到 10 条分解住院记录"
    assert getattr(res, "usage_metadata", None) is not None  # 自动补全 token 估算


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_resilient_chat_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ResilientChatModel' from 'app.infra.enriched_llm'`

- [ ] **Step 3: Implement ResilientChatModel in `app/infra/enriched_llm.py`**

在 `app/infra/enriched_llm.py` 中实现 `ResilientChatModel`：
```python
class ResilientChatModel(BaseChatModel):
    """
    [Phase 1] 统一韧性模型装饰器：
    消除供应商子类继承，通过组合代理原生 BaseChatModel，
    集中处理：Anti-Chat 拦截、Claude 结构化内容归一化、Token 用量估算补全、429 指数退避重试与切流上报。
    """
    inner_model: BaseChatModel
    endpoint_id: str = "unknown"
    max_retries: int = 2
    backoff_base: float = 2.0  # 重试退避基数 (秒)

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return f"resilient-{getattr(self.inner_model, '_llm_type', 'unknown')}"

    def _enrich_result(self, result: ChatResult, messages: List[BaseMessage]) -> None:
        """强化结果：Anti-Chat 闲聊检测、Claude 内容扁平化与 Token 估算"""
        _is_probe = (
            len(messages) == 1
            and hasattr(messages[0], "content")
            and str(messages[0].content).strip().lower() in ("ping", "1", "hi", "test")
        )

        for gen in result.generations:
            msg = gen.message
            # 1. Claude/Thinking 内容归一化
            if isinstance(msg.content, list):
                text_parts = []
                for item in msg.content:
                    if isinstance(item, str):
                        if item: text_parts.append(item)
                    elif isinstance(item, dict):
                        if item.get("type") == "text" and item.get("text"):
                            text_parts.append(item["text"])
                        elif "text" in item and item["text"]:
                            text_parts.append(item["text"])
                if text_parts or not getattr(msg, "tool_calls", None):
                    msg.content = "\n".join(text_parts).strip()

            # 2. Anti-Chat Guard: 过滤无意义闲聊废话
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

    def _should_ignore_breaker(self, err_msg: str) -> bool:
        """400 InvalidParameter 等请求级错误不熔断节点"""
        return "InvalidParameter" in err_msg or "Invalid messages" in err_msg

    async def _agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs
    ) -> ChatResult:
        attempt = 0
        while True:
            try:
                result = await self.inner_model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
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
        while True:
            try:
                result = self.inner_model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_resilient_chat_model.py -v`
Expected: 5 passed in < 0.5s

- [ ] **Step 5: Commit Task 1**

```bash
git add app/infra/enriched_llm.py tests/unit/test_resilient_chat_model.py
git commit -m "refactor: introduce ResilientChatModel decorator in enriched_llm"
```

---

### Task 2: 实现向后兼容工厂函数与平滑绞杀过渡

**Files:**
- Modify: `app/infra/enriched_llm.py`
- Test: `tests/unit/test_resilient_chat_model.py`

**Interfaces:**
- Consumes: `ResilientChatModel`, `ChatOpenAI`, `ChatGoogleGenerativeAI`, `ChatAnthropic`
- Produces: `EnrichedChatOpenAI(**kwargs) -> ResilientChatModel`, `EnrichedChatGoogleGenerativeAI(**kwargs) -> ResilientChatModel`, `EnrichedChatAnthropic(**kwargs) -> ResilientChatModel`

- [ ] **Step 1: Write test for backward-compatible factory functions**

在 `tests/unit/test_resilient_chat_model.py` 追加：
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_resilient_chat_model.py::test_transitional_factory_functions -v`
Expected: FAIL (because factory functions or endpoint_id handling not implemented yet).

- [ ] **Step 3: Implement transitional factory functions in `app/infra/enriched_llm.py`**

将旧的 `EnrichedChatOpenAI`、`EnrichedChatGoogleGenerativeAI`、`EnrichedChatAnthropic` 替换为：
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_resilient_chat_model.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit Task 2**

```bash
git add app/infra/enriched_llm.py tests/unit/test_resilient_chat_model.py
git commit -m "refactor: convert EnrichedChat subclasses into transitional factory functions"
```

---

### Task 3: 清理 `model_manager.py` 中的 Pydantic 黑客补丁并全面验收

**Files:**
- Modify: `app/infra/model_manager.py:180-215`
- Test: `tests/unit/test_container.py`, `tests/unit/test_resilient_chat_model.py`

**Interfaces:**
- Consumes: `EnrichedChatOpenAI(..., endpoint_id=name)`
- Produces: Clean LLM instantiation without `object.__setattr__`

- [ ] **Step 1: Check existing object.__setattr__ occurrences in model_manager.py**

查看 `app/infra/model_manager.py:180-215` 中的 3 处 `object.__setattr__(llm, 'endpoint_id', name)`。

- [ ] **Step 2: Clean up model_manager.py**

修改 `app/infra/model_manager.py`，将 `endpoint_id=name` 直接作为参数传给构造器，并删除 `object.__setattr__`：
```python
            if provider == "google":
                return EnrichedChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=api_key,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    endpoint_id=name
                )
            elif provider == "anthropic":
                base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "http://103.236.76.197:11223/anthropic")
                return EnrichedChatAnthropic(
                    model_name=model_name,
                    anthropic_api_key=api_key,
                    anthropic_api_url=base_url,
                    temperature=temperature,
                    timeout=120.0,
                    streaming=True,
                    endpoint_id=name
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
                    endpoint_id=name
                )
```

- [ ] **Step 3: Run all unit tests to verify zero regressions**

Run: `python -m pytest tests/unit/ -v`
Expected: All unit tests pass with 0 errors.

- [ ] **Step 4: Commit Task 3**

```bash
git add app/infra/model_manager.py
git commit -m "refactor: clean up endpoint_id Pydantic hacks in model_manager"
```

---

## Plan Self-Review Checklist
- [x] Spec coverage: Covers ResilientChatModel, transitional factory functions, model_manager clean-up.
- [x] No placeholders: All step code snippets are fully written.
- [x] Type consistency: Function signatures and method calls match across all 3 tasks.
- [x] Verifiable: Every task contains a test-driven verification step.
