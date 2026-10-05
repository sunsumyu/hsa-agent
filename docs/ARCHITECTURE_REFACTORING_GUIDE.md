# Argus 架构重构与工程设计指南 (Architecture & Refactoring Guide)

> **基于 Martin Fowler《重构：改善既有代码的设计》与《演进式架构》体系**  
> **面向国家医保局 (HSA) 多智能体复杂审计场景设计**

---

## 目录
1. [核心重构哲学：确定性与概率性的接缝 (Seam)](#1-核心重构哲学确定性与概率性的接缝-seam)
2. [既有代码坏味道诊断与章节对应 (Code Smells)](#2-既有代码坏味道诊断与章节对应-code-smells)
3. [目标架构：SOLID 原则与设计模式落地](#3-目标架构solid-原则与设计模式落地)
4. [平滑演化：四阶段绞杀者演进路线图](#4-平滑演化四阶段绞杀者演进路线图)
5. [架构适应度函数与自动化看门狗 (Fitness Functions)](#5-架构适应度函数与自动化看门狗-fitness-functions)
6. [Code Review 10 秒架构门禁清单 (Gate Checklist)](#6-code-review-10-秒架构门禁清单-gate-checklist)

---

## 1. 核心重构哲学：确定性与概率性的接缝 (Seam)

在传统的软件工程中，重构主要服务于**人类程序员的可维护性与自动化单测**。而在 LLM Agentic 架构中，重构更是为了**抑制大模型幻觉、降低 Token 成本并锁定物理执行的确定性**。

### 1.1 确定性三明治架构 (Deterministic Sandwich)
大模型擅长**跨多表的模糊语义推理与复杂业务对碰逻辑推演**（概率性），但极不擅长**机械字段匹配、字符串拼装与物理安全防范**（确定性）。重构的核心目标是将接缝（Seam）外露：

```
                    ┌────────────────────────────────────────┐
                    │      上层确定性护栏 (Deterministic)       │
                    │  - Schema 物理映射 (SchemaManager)      │
                    │  - 场景-表硬性绑定 (SceneTableSelector)  │
                    │  - 静态高频规则旁路 (FastRouter)         │
                    └───────────────────┬────────────────────┘
                                        │ (干净的提示词与最小物理上下文)
                                        ▼
                    ┌────────────────────────────────────────┐
                    │       中枢概率性推理 (Probabilistic)      │
                    │  - CoderAgent: 只专注业务对碰逻辑生成   │
                    │  - PlannerAgent: 专注任务目标拆解      │
                    └───────────────────┬────────────────────┘
                                        │ (生成的原始 SQL 与方法论)
                                        ▼
                    ┌────────────────────────────────────────┐
                    │      下层确定性执行 (Deterministic)       │
                    │  - AST 语法树安全阻断 (SQLGuardian)    │
                    │  - 租户行政区划强制注入 (TenantInjector) │
                    │  - 零行判定与降级熔断 (FallbackGate)    │
                    └────────────────────────────────────────┘
```

---

## 2. 既有代码坏味道诊断与章节对应 (Code Smells)

对标 Martin Fowler《重构》（第 2 版）经典目录，当前工程关键痛点对齐如下：

| 代码坏味道 | 典型定位 (File & Line) | 危害分析 | 对应书中章节与重构手法 |
| :--- | :--- | :--- | :--- |
| **3.3 过长函数 (Long Function)**<br>**3.20 过大的类 (Large Class)** | `app/agents/coder_agent.py:55-300`<br>(`execute` 单函数 240+ 行) | 混杂跟踪、重试、直通、清洗、拼装、调度、校验等 8 种关注点，认知负荷极高，无法单独单测 | **6.1 提炼函数 (Extract Function)**<br>**6.11 拆分阶段 (Split Phase)**<br>**10.3 以卫语句取代嵌套 (Guard Clauses)** |
| **3.8 霰弹式修改 (Shotgun Surgery)**<br>**3.7 发散式变化 (Divergent Change)** | `app/skills/fast_router.py`<br>`app/core/scene_table_selector.py`<br>`app/reporting/policy_matcher.py` | 医保场景关键词在 3 个文件重复硬编码；法规更新需同时修改 4 处，漏改即产生严重隐蔽缺陷 | **8.1 搬移函数 (Move Function)**<br>**8.2 搬移字段 (Move Field)**<br>**10.4 以表驱动取代条件 (Table-Driven)** |
| **3.11 基本类型偏执 (Primitive Obsession)**<br>**3.10 数据泥团 (Data Clumps)** | `app/core/context/gates.py:64-68`<br>(`"DROP" in sql`)<br>`app/core/state.py` (松散字典) | 原始字符串子串判断易将字段名误判为高危 SQL；全局 state 在各节点随意 `pop`，缺乏可重入性 | **7.1 封装记录 (Encapsulate Record)**<br>**7.3 以对象取代基本类型**<br>**7.7 隐藏委托关系 (Hide Delegate)** |
| **3.23 被拒绝的遗赠 (Refused Bequest)**<br>**滥用继承** | `app/infra/enriched_llm.py:23-160`<br>(继承 `ChatOpenAI`, `ChatGoogle`) | 为增加重试与防闲聊强行继承第三方类，复制粘贴几乎相同的限流代码，导致同步/异步混用隐患 | **12.10 以委托取代子类 (Replace Subclass with Delegate)**<br>**组合优于继承 (Decorator Pattern)** |
| **3.2 重复代码 (Duplicated Code)**<br>**3.15 夸夸其谈通用性 / 死代码** | `isinstance(m, tuple)...` 分散 4 处<br>`app/skills/sql_validator.py:88-89` | 消息角色嗅探逻辑多处重复；存在不可达的重复 `return True, ""`，YAML 缺乏只读缓存 | **6.1 提炼工具函数**<br>**8.9 移除死代码 (Remove Dead Code)** |

---

## 3. 目标架构：SOLID 原则与设计模式落地

### 3.1 编排层：管道与过滤器模式 (Pipeline & Filters Pattern)
消除 `coder_agent.py` 的平铺长函数，每个处理阶段抽象为纯粹的 `PipelineStep`：

```python
# 核心编排器蜕变为极简调度器 (代码控制在 25 行内)
async def execute(self, state: AuditState, config: RunnableConfig) -> Dict[str, Any]:
    # 1. 卫语句守卫
    if self._has_exceeded_retries(state):
        return self._make_retry_limit_response(state)

    # 2. 静态快速路由旁路 (命中且非空则直通，否则平滑降级)
    fast_route_res, state = await self._try_fast_route_execution(state, config)
    if fast_route_res is not None:
        return fast_route_res

    # 3. 管道化流转：上下文构建 ➔ 模型推理 ➔ 工具执行 ➔ 质量门控
    return await self._execution_pipeline.run(state, config)
```

### 3.2 基础设施层：装饰器与端口适配器模式 (Decorator & Adapter)
消除供应商子类继承体系，将横切关注点（Cross-Cutting Concerns）收拢为可组装的装饰器栈：

```python
# 统一的领域端口
class ChatPort(Protocol):
    async def generate(self, messages: List[BaseMessage], **kwargs) -> AIMessage: ...

# 核心适配器持有着原生 LangChain 实例 (委托模式)
# 外部堆叠独立装饰器：
# Client -> RateLimitRetryDecorator -> AntiChatGuardDecorator -> TokenEnrichmentDecorator -> BaseChatAdapter
```

### 3.3 领域规则层：规约模式与仓储模式 (Specification & Repository)
将 `policy_matcher.py` 中 840 行的硬编码 `if-else` 解耦为声明式配置：
* 配置文件：`configs/audit_scenarios.yaml`（单一事实源 SSOT）；
* 领域实体：`AuditScenarioRule`，自包含 `is_satisfied_by(user_query)` 规约判定；
* 仓储门面：`ScenarioRuleRepository`，同时为 `fast_router`、`scene_table_selector` 和 `policy_matcher` 提供查询支撑。

### 3.4 安全与门控层：AST 拦截器模式 (AST Interceptor Pattern)
遵循**迪米特法则 (Law of Demeter)**，禁止外部组件操作原始 SQL 字符串：
* 统一由 `SQLASTInspector` 一次性完成 AST 解析；
* 链式挂载 `SecurityInterceptor`、`ComplexityInterceptor`、`GovernanceInterceptor`；
* 输出只读的 `SQLInspectionReport` 给 `QualityGate` 做决策。

---

## 4. 平滑演化：四阶段绞杀者演进路线图

遵循 Martin Fowler **“重构绝不可推倒重来，必须步步可验证”** 的铁律：

```
Phase 1: 基础设施解耦 (风险: ★☆☆☆☆)
  └── 以 Decorator 包装原生 LLM，保持旧 EnrichedChatOpenAI 接口不变（内部改为委托）
      │
Phase 2: 领域知识外置 (风险: ★★☆☆☆)
  └── 抽取 ScenarioRuleRepository，match_policies() 内部改为调用仓储，对外签名不变
      │
Phase 3: 安全门控统合 (风险: ★★☆☆☆)
  └── QualityGate.evaluate_risk 切换至 AST 检查报告，消除 "DROP" in sql 误伤
      │
Phase 4: 核心流程管道化 (风险: ★★★☆☆)
  └── CoderAgent.execute 逐步提炼为独立 PipelineStep，配合黄金快照测试守护
```

### 4.1 安全网：黄金主记录测试 (Golden Master Tests)
在修改任何业务逻辑前，先录制典型场景的输入与输出快照（`tests/unit/characterization/`）：
* 冻结生成的 SQL 语法树规范化形式；
* 冻结返回的关键 Trace 与 Report 数据格式；
* 每次微步重构只要快照比对无误，即证明重构达到“不改变外部行为”的严格定义。

---

## 5. 架构适应度函数与自动化看门狗 (Fitness Functions)

将架构约束直接写入自动化测试，防止未来代码退化：

### 5.1 状态不可变看门狗 (`tests/architecture/test_state_guard.py`)
```python
def test_no_in_place_state_mutation_in_agents():
    """静态检查：严禁在 Agent 节点内调用 state.pop() 或原地分配 state[k] = v"""
    ...
```

### 5.2 圈复杂度与行数看门狗 (`tests/architecture/test_complexity_guard.py`)
```python
def test_agent_methods_cyclomatic_complexity():
    """静态检查：所有 Agent 执行函数圈复杂度必须 <= 8，函数代码行数必须 <= 60"""
    ...
```

### 5.3 原始 SQL 字符串检查看门狗 (`tests/architecture/test_sql_guard.py`)
```python
def test_no_raw_sql_substring_matching():
    """静态检查：严禁使用 'DROP' in sql 检查风险，必须委托给 AST Inspector"""
    ...
```

---

## 6. Code Review 10 秒架构门禁清单 (Gate Checklist)

所有涉及智能体核心代码的 Pull Request，必须通过以下 5 道硬性门禁：

- [ ] **门禁 1：无长函数与步骤注释** —— 单一函数代码行数未超过 50 行，没有出现通过 `# 步骤一`、`# 步骤二` 隔离逻辑的代码块（必须提炼为具名函数）。
- [ ] **门禁 2：无直接字典篡改** —— 没有在节点内部调用 `state.pop()` 或无保护的深层字典索引（必须通过领域上下文传递）。
- [ ] **门禁 3：无原始 SQL 字符串探查** —— 没有出现 `f"SELECT ... {filter}"` 或 `"DELETE" in sql`（必须使用 AST 验证）。
- [ ] **门禁 4：无硬编码业务规约** —— 没有在 Python 代码中内联医保关键词或法规条款（必须声明在 YAML 规则库中）。
- [ ] **门禁 5：严格分离两顶帽子** —— PR 纯粹为结构重构，未混入新业务功能逻辑。

---
*Powered by DeepMind Advanced Agentic Coding Team & Martin Fowler Refactoring Framework*
