# 神经符号门禁（Neuro-Symbolic Guardrails）与智能体系统工程演进指南

> **文档定位**：本文档沉淀了 Argus-Agent 项目在解决复杂排斥违规场景（如主客体混淆、恒假条件生成、执行空集灾难）中的核心方法论，融合了行业开源标杆（`hello-agents` 2026 最新演进）、Matt Pocock 深模块设计原则与神经符号（Neuro-Symbolic）AI 架构实践，作为全团队长期遵循的工程指南。

---

## 目录
1. [问题复盘：为什么纯 Prompt 机制无法解决逻辑灾难？](#1-问题复盘为什么纯-prompt-机制无法解决逻辑灾难)
2. [理论基石：神经符号（Neuro-Symbolic）架构体系](#2-理论基石神经符号neuro-symbolic架构体系)
3. [前沿映射：Hello-Agents 最新演进与系统工程启示](#3-前沿映射hello-agents-最新演进与系统工程启示)
4. [核心落地：Argus-Agent 的三大深度模块实践](#4-核心落地argus-agent-的三大深度模块实践)
5. [架构原则：Matt Pocock 深模块与单一事实源（SSOT）](#5-架构原则matt-pocock-深模块与单一事实源ssot)
6. [长效演进：从单点门禁到多原型自愈体系的拓展指南](#6-长效演进从单点门禁到多原型自愈体系的拓展指南)

---

## 1. 问题复盘：为什么纯 Prompt 机制无法解决逻辑灾难？

### 1.1 经典缺陷场景（QA-SCOPE-02 男性使用女性专属宫内节育器）
在医保违规审计中，典型的逻辑冲突表现在：
* **业务常识**：宫内节育器（客体）仅适用于女性，因此**男性使用该项目构成违规**。
* **审计目标**：筛选出**使用了该项目的男性患者**。
* **模型失控路径**：
  1. 模型在同一 Prompt 中看到了“男性”与“女性专属项目”；
  2. 产生“反向排除”混乱，误以为要同时把不属于合规范围的属性全部排除；
  3. 最终生成：`WHERE hilist_name LIKE '%宫内节育%' AND gend NOT LIKE '1%' AND gend NOT LIKE '2%'`；
  4. 导致全表无任何数据命中（恒假谓词，False Positive/Negative），但由于语法完全符合 ClickHouse 规范，传统执行引擎静默返回 0 行，造成严重的漏检。

### 1.2 纯 Prompt 堆叠的致命缺陷（Prompt Bloating & Stochastic Failure）
许多团队在遭遇上述问题时的第一反应是“加 Prompt”：
* 在 System Prompt 中增加补丁：“*绝对不能写 gend NOT LIKE '1%' AND NOT LIKE '2%'*”、“*注意主体是男性*”。
* **为什么这必然失效？**
  1. **概率本质（Stochasticity）**：LLM 本质是基于 Token 概率采样的预测器。当需求变长、上下文变复杂时，注意力权重（Attention Weights）会发生漂移；
  2. **提示词膨胀（Prompt Bloating）**：每出一个 Bug 就加几行约束，Prompt 越来越冗长，相互矛盾的指令增多，最终导致模型遵循率断崖式下跌；
  3. **LLM-as-a-Judge 的局限**：如果仅用另一个 LLM 进行代码评审，本质上是**“用概率去检验概率”**，在边界条件下依然会发生同频幻觉。

---

## 2. 理论基石：神经符号（Neuro-Symbolic）架构体系

神经符号 AI 是将**连接主义（Neural Networks / LLM）**与**符号主义（Symbolic AI / 规则与形式逻辑）**相结合的体系，在智能体领域实现了 System 1 与 System 2 的完美分工：

```
                    ┌──────────────────────────────────────────────┐
                    │            自然语言输入 (开放、模糊)            │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 神经系统 (Neuro / LLM) - 快思考 (System 1)                                          │
│ • 职责：自然语言意图理解、复杂概念映射、业务实体提取、生成代码草案                     │
│ • 特征：高泛化、容忍模糊输入，但缺乏确定性逻辑保证                                    │
└──────────────────────────────────────┬───────────────────────────────────────────┘
                                       │ 产出代码/SQL草案
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 符号系统 (Symbolic Gate) - 慢思考 (System 2)                                      │
│ • 职责：静态 AST 语法树解析、一阶谓词逻辑推导、集合论全集校验、强类型断言            │
│ • 特征：100% 确定性、零幻觉、数学证明，但在语义理解上僵硬                            │
│ • 工具：sqlglot AST、布尔化简、Schema Registry 物理枚举契约                        │
└───────────────────┬──────────────────────────────────────────┬───────────────────┘
                    │ 发现矛盾 (恒假/全排斥/越界)               │ 校验 100% 通过
                    ▼                                          ▼
┌─────────────────────────────────────────┐   ┌────────────────────────────────────┐
│ 结构化反思引擎 (Diagnostic Feedback)    │   │ 物理数据库 / 真实执行环境           │
│ • 注入精准、紧凑的符号诊断反馈           │   │ • ClickHouse / 业务流水线          │
│ • 隔离脏历史，触发自愈修复步进           │   └────────────────────────────────────┘
└───────────────────┬─────────────────────┘
                    │
                    └─────── 重新生成 (Refinement Loop) ────────┘
```

### 符号门禁的核心公理
1. **二元枚举全否定恒假律**：
   设业务字段 $C$ 的定义全集为 $\Omega = \{v_1, v_2\}$（如性别全集 $\{1, 2\}$）。若查询条件施加了：
   $$\neg (C = v_1) \land \neg (C = v_2) \implies C \notin \Omega \implies \text{WHERE } \text{False}$$
   该条件在逻辑学上等价于恒假（Contradiction），符号系统必须在物理执行前无条件硬拦截。
2. **标量互斥律**：
   在同一单行记录粒度上，若对同一确定标量施加等值互斥：
   $$(C = a) \land (C = b) \quad (\text{其中 } a \neq b) \implies \text{False}$$
   符号门禁直接拒绝，防止生成无效查询。

---

## 3. 前沿映射：Hello-Agents 最新演进与系统工程启示

从开源标杆 `hello-agents`（Datawhale 开源智能体系统，2026 最新架构体系）的代码与工程提交中，我们可以提炼出四条至关重要的生产级智能体准则：

### 3.1 准则一：Agent Skills 按需挂载代替 Prompt 全量堆叠
* **Hello-Agents 实践**：在 2026 年合并的成熟项目（如 PR #938 `PaperGraph`）中，系统不再把所有专有领域的处理规则写死在全局 System Prompt 里，而是将阅读、代码审查、API 测试等功能解耦为**按需加载的 Skill 机制**。
* **对 Argus 的映射**：将“性别排斥审计”、“时序违规审计”等特定逻辑做成独立规划器与门禁插件，只在场景被识别时激活，保持核心 LLM 提示词的纯净与轻量。

### 3.2 准则二：上下文隔离与避免错误重放（Anti-Error-Replay）
* **Hello-Agents 实践**：在重试纠错链路中，**严格控制上下文预算**（单次上下文设定字节上限），严禁将动辄数千字节的模型失败回复或大段报错堆栈原封不动地回灌重放。重放会导致模型陷入对自身错误的注意力强化（Error Reinforcement Loop）。
* **对 Argus 的映射**：[AuditReflectionEngine](file:///f:/chain/argus-agent/app/core/reflection/audit_reflection_engine.py) 生成的反馈必须是**高度提炼的结构化诊断**（如：`"字段 gend 包含了全集排除，请改为正向筛选 gend LIKE '1%'"`），而不是把整个错误的 SQL 和数据库全部上下文无脑堆叠。

### 3.3 准则三：走向 Schema 强契约（AgentScope 2.0 升级启示）
* **Hello-Agents 实践**：Chapter 6 全面拥抱 AgentScope 2.0，核心在于弃用模糊的自由文本管道，全面采用 `structured_schema` 与 `structured_output` 契约，结合现代 MCP 协议。
* **对 Argus 的映射**：Prompt 中绝不让模型猜测字段含义或枚举值；必须通过权威 [schema_registry.yaml](file:///f:/chain/argus-agent/configs/schema_registry.yaml) 与 [CONTEXT.md](file:///f:/chain/argus-agent/CONTEXT.md) 作为单一事实源，通过结构化意图（`IntentPlan`）进行强约束。

### 3.4 准则四：Evaluator-Optimizer 与强化自愈闭环
* **Hello-Agents 实践**：Chapter 11 (Agentic-RL) 与 Chapter 4 (Reflection / Evaluator-Optimizer) 强调，单次预测的准确率存在天花板，必须具备环境反馈（Reward/Evaluation）驱动的闭环优化能力。
* **对 Argus 的映射**：在执行层捕获到 0 命中时，不将其视作终态，而是触发 Critic 评审机制，判定是真实合规还是逻辑颠倒，如果是逻辑颠倒则启动自愈步进。

---

## 4. 核心落地：Argus-Agent 的三大深度模块实践

基于上述理论，我们在 `argus-agent` 中构建了三道坚固的工程防线：

### 4.1 深度模块一：静态 AST 恒假矛盾检测器 (`ContradictionDetector`)
* **定位**：符号门禁核心（Symbolic Gate）。
* **源码**：[app/core/guardrails/contradiction_detector.py](file:///f:/chain/argus-agent/app/core/guardrails/contradiction_detector.py)
* **挂载点**：[app/core/context/gates.py](file:///f:/chain/argus-agent/app/core/context/gates.py) 中的 `QualityGate.validate_sql_semantics`，以及 `SQLGuardian.validate_sql`。
* **技术实现**：
  * 使用 `sqlglot` 将 SQL 语法树深度解析为 AST；
  * 遍历提取所有 `WHERE` 谓词子树中的否定条件（`NOT LIKE`、`!=`、`NOT IN`）；
  * 对已知枚举字典（如 `gend` 的 `{'1', '2'}`）执行集合覆盖率推导；
  * 一旦发现集合被 100% 排除，或存在同一字段标量冲突，立即抛出 `ContradictionViolation`，物理阻断查询下发。

### 4.2 深度模块二：意图规划与认知解耦器 (`AuditIntentPlanner`)
* **定位**：神经系统的 Plan-and-Solve 分层引擎。
* **源码**：[app/core/planning/audit_intent_planner.py](file:///f:/chain/argus-agent/app/core/planning/audit_intent_planner.py)
* **挂载点**：[app/agents/coder_agent.py](file:///f:/chain/argus-agent/app/agents/coder_agent.py) 代码生成流水线前置阶段。
* **技术实现**：
  * 将“写 SQL”前置拆解为“业务意图抽象”；
  * 强制区分三大要素：
    1. **审计主体（Audit Target）**：违规人是谁（如：男性 `gend LIKE '1%'`）；
    2. **客体特征（Violation Object）**：违规项目是什么（如：宫内节育器）；
    3. **原型分类（Archetype）**：互斥排他、时序重叠、频次离群、伴随缺失；
  * 将规划结果格式化为显式提示块，注入 CoderAgent，从源头上阻止模型混淆主客体。

### 4.3 深度模块三：执行后验反思自愈引擎 (`AuditReflectionEngine`)
* **定位**：Evaluator-Optimizer 闭环守护者。
* **源码**：[app/core/reflection/audit_reflection_engine.py](file:///f:/chain/argus-agent/app/core/reflection/audit_reflection_engine.py)
* **挂载点**：Coder 质量门禁与执行诊断通道。
* **技术实现**：
  * 监听 SQL 真实执行结果；
  * 当场景属于**互斥排他型（Exclusion）**且执行结果**精准为 0 行**时，激活深度研判；
  * 检查 SQL 的 `WHERE` 子句是否颠倒了主客体约束；
  * 输出规范化 `DiagnosticFeedback`，精准指导模型在单次会话内进行靶向自愈重写。

---

## 5. 架构原则：Matt Pocock 深模块与单一事实源（SSOT）

在代码组织与维护上，全系统严格遵守 Matt Pocock 提出的**深模块原则（Deep Modules）**：

| 设计维度 | 传统浅模块反模式（Shallow Module） | Matt Pocock 深模块典范（Deep Module） |
| :--- | :--- | :--- |
| **接口形态** | 臃肿暴露：调用方需要传递 AST 对象、枚举列表、SQL 上下文 | **极简窄接口（Narrow Interface）**：`detector.detect(sql: str) -> Optional[Violation]` |
| **内部封装** | 业务逻辑泄漏：调用方自己写 `sqlglot` 遍历和 if-else 判断 | **深度隐藏复杂度**：内部封装复杂的 AST 递归、运算符优先级、集合代数计算 |
| **变更影响** | 外部脆弱：修改解析库版本导致几十处调用方报错 | **外部零震荡**：更换底层解析器时，外部仅依赖布尔或结构体返回值 |
| **信息源管理** | 各处散落：各个 Prompt 和 Python 文件硬编码 `'1'` 是男 `'2'` 是女 | **单一事实源（SSOT）**：统一由 [CONTEXT.md](file:///f:/chain/argus-agent/CONTEXT.md) 与 `schema_registry.yaml` 权威仲裁 |

---

## 6. 长效演进：从单点门禁到多原型自愈体系的拓展指南

当前落地的门禁体系不仅服务于“性别互斥”场景，更为未来新增场景提供了标准的扩展范式：

```
                              新增业务审计场景
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
   1. 扩展符号门禁规则 (Symbolic)                  2. 扩展意图规划原型 (Intent)
   • 时序重叠型：                                   • 在 CONTEXT.md 补充原型定义
     拦截 adm_time > dscg_time                      • 在 SchemaRegistry 补充时序字段
     拦截 同一身份证异地重叠住院                      • 在 Planner 注入主体时序校验
   • 伴随依赖型：                                   • 在 Evaluator 注入级联核对逻辑
     拦截 依赖收费缺失前置主手术
```

### 研发自检四步法（Checklist）
在引入新的复杂业务审计规则时，必须依序完成：
1. [ ] **文档先行（DDD）**：在 [CONTEXT.md](file:///f:/chain/argus-agent/CONTEXT.md) 中登记该业务的核心主体、客体与原型分类，杜绝私下定义；
2. [ ] **测试驱动（TDD）**：在 `tests/unit/` 中编写红灯测试用例（包括恶意的颠倒条件与合法查询）；
3. [ ] **符号门禁注入**：在 `ContradictionDetector` 或对应 AST 校验器中添加形式化推导规则，跑通绿灯；
4. [ ] **隔离闭环验证**：确保反思引擎的反馈短小精炼，严禁向模型回灌未经清洗的脏历史。
