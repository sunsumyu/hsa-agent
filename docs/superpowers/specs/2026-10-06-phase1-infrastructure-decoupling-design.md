# Phase 1 架构重构设计文档：基础设施解耦与 ResilientChatModel 统一装饰器

- **日期**：2026-10-06
- **模块**：`app/infra/enriched_llm.py` & `app/infra/model_manager.py`
- **目标**：以组合（Composition / Decorator Pattern）取代对外部第三方供应商 SDK 的派生继承，消除重复代码与异步阻塞隐患，实现 100% 平滑过渡。

---

## 1. 现状痛点与重构动因

### 1.1 现状架构分析
在原 `app/infra/enriched_llm.py` 中，分别定义了三个类：
* `EnrichedChatOpenAI(ChatOpenAI)`
* `EnrichedChatGoogleGenerativeAI(ChatGoogleGenerativeAI)`
* `EnrichedChatAnthropic(ChatAnthropic)`

### 1.2 核心缺陷（Bad Smells）
1. **违背开闭原则（OCP）与滥用继承（Refused Bequest）**：
   * 为了附加横切关注点（429 限流重试、闲聊过滤、Token 补全），直接继承外部第三方库的具象类；
   * 每新增一家模型供应商（如 DeepSeek、百炼、智谱），都需要新写一个子类并复制全部重试和过滤逻辑。
2. **重复代码（Duplicated Code）**：
   * 三个子类各自定义了几乎一模一样的 `_agenerate`、`_generate` 异常捕获块和 429 退避逻辑。
3. **Pydantic 属性黑客写法（Pydantic Hack）**：
   * 在 `model_manager.py` 中，为了给子类附加 `endpoint_id`，被迫使用 `object.__setattr__(llm, 'endpoint_id', name)` 绕过 Pydantic extra-fields 检查。
4. **异步/同步阻塞混用隐患（FIXES.md P1 Issue）**：
   * 同步方法 `_generate` 中使用了 `time.sleep`，异步方法 `_agenerate` 中使用了 `asyncio.sleep`，在并发事件循环中存在潜在阻塞风险。

---

## 2. 目标架构设计

### 2.1 模式选择：装饰器模式（Decorator Pattern）与适配器（Adapter）
放弃类继承，采用对象组合：定义一个通用的 `ResilientChatModel`，包装任意原生的 LangChain `BaseChatModel`。

```
                     Client Call (LLMProvider / Agent)
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │      ResilientChatModel       │  (统一装饰器)
                   │  - 显式声明 endpoint_id       │
                   │  - Anti-Chat 闲聊拦截         │
                   │  - 财务级 Token 用量估算补全   │
                   │  - 内容结构归一化 (Anthropic) │
                   │  - 统一 429 退避重试与熔断    │
                   └───────────────┬───────────────┘
                                   │ delegates to
                                   ▼
                   ┌───────────────────────────────┐
                   │    原生 BaseChatModel 实例     │
                   │ (ChatOpenAI / ChatAnthropic.. │
                   └───────────────────────────────┘
```

### 2.2 核心契约与处理管道

```python
class ResilientChatModel(BaseChatModel):
    """
    统一韧性模型装饰器：
    持有原生的 inner_model，负责横切关注点的透明代理与治理。
    """
    inner_model: BaseChatModel
    endpoint_id: str
    max_retries: int = 2
```

#### 横切关注点管道职责：
1. **调用委托**：
   * 异步调用 `_agenerate` 委托给 `inner_model.agenerate`；
   * 同步调用 `_generate` 委托给 `inner_model.generate`；
   * 流式生成 `_astream` / `_stream` 纯透传给 `inner_model`。
2. **结果强化（_enrich_result）**：
   * **Anti-Chat 检验**：扫描生成文本是否包含 `["你好", "很高兴为您服务", "我是一个大语言模型", "作为一个AI", "有什么可以帮您", "抱歉"]`，且非探活消息（`"ping"`, `"1"` 等），命中则抛出 `ValueError` 并记录失败；
   * **内容归一化**：如果 `msg.content` 是字典列表（Anthropic 格式），自动拼接为纯文本字符串；
   * **用量估算补全**：若 `msg.usage_metadata` 缺失，通过 `usage_tracker._estimate_tokens` 估算并填补 `input_tokens`、`output_tokens`、`total_tokens`。
3. **异常与重试治理（_handle_exception）**：
   * 针对 400 Bad Request（请求级错误，如参数格式不当），直接 raise，**不触发熔断**；
   * 针对 429 / Rate Limit，执行指数退避重试（最多 2 次）；
   * 针对配额耗尽或硬性错误，调用 `endpoint_pool_manager.record_failure(self.endpoint_id, str(e))`，触发熔断切流。

---

## 3. 平滑过渡与向后兼容（Strangler Fig Transition）

为了保证项目既有调用代码零感知、零破坏：
* 在 `app/infra/enriched_llm.py` 中保留 `EnrichedChatOpenAI`、`EnrichedChatGoogleGenerativeAI`、`EnrichedChatAnthropic` 作为**向后兼容的工厂函数（Factory Functions）**：
  ```python
  def EnrichedChatOpenAI(**kwargs) -> ResilientChatModel:
      endpoint_id = kwargs.pop("endpoint_id", "unknown")
      raw_llm = ChatOpenAI(**kwargs)
      return ResilientChatModel(inner_model=raw_llm, endpoint_id=endpoint_id)
  ```
* 在 `model_manager.py` 中：
  * 直接通过 `endpoint_id` 参数传入，彻底移除所有的 `object.__setattr__(llm, 'endpoint_id', name)` 黑客补丁。

---

## 4. 单元测试与验证计划

在 `tests/unit/test_resilient_chat_model.py` 中编写 5 组关键测试用例：
1. **测试正常透传**：输入标准 HumanMessage，验证返回结果与底层模型一致；
2. **测试 Anti-Chat 拦截**：模拟返回“你好，有什么可以帮您”，验证成功被拦截并抛出异常，同时记录了 failure；探活消息 "ping" 则正常放行；
3. **测试 429 智能重试**：底层模型前 1 次抛出 429，第 2 次成功返回，验证装饰器平滑自愈；
4. **测试 Token 缺失补全**：底层模型返回 usage 为空时，验证 `msg.usage_metadata` 被自动注入估算值；
5. **测试工厂函数兼容性**：验证 `EnrichedChatOpenAI(...)` 创建出的模型能够正常被 LangChain `Runnable` 链条调度（支持 `.bind_tools`、`.with_fallbacks`）。

---

## 5. 验收标准
1. `tests/unit/test_resilient_chat_model.py` 全绿通过；
2. 既有测试用例（`tests/unit/test_container.py`、`test_fast_router.py` 等）100% 保持通过；
3. `app/infra/enriched_llm.py` 代码行数精简，重复代码彻底消除；
4. 消除 `FIXES.md` 中记录的 `P1 异步阻塞混用` 隐患。
