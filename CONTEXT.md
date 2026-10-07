# HSA 医保智能审计系统上下文术语表 (Domain Context & Glossary)

> **单一体现源契约 (Single Source of Truth)**: 本文件为整个 Argus-Agent 项目在领域模型、审查逻辑与防腐机制上的权威定义。任何涉及模型意图推导、SQL 校验及评测的逻辑必须与本定义严格一致。

---

## 1. 核心领域实体 (Core Domain Entities)

### 1.1 审计主体 (Audit Subject / Target)
- **定义**：医保违规行为的发生载体，即规则所要筛查的目标人群、机构或单据主体。
- **正向标识**：在医保基金审计中，主体条件必须作为正向约束进入 `WHERE` 子句。
  - 例如在“男性使用女性专属宫内节育器”场景中，**主体是男性**（`gend = '1'` 或 `gend LIKE '1%'`）。
- **违规反模式 (Anti-pattern)**：将违规客体的特征泛化到主体上，导致主体被排除（例如错误地写出 `gend NOT LIKE '1%'` 或 `gend NOT LIKE '2%'`）。

### 1.2 违规客体特征 (Violation Feature / Object)
- **定义**：主体所接受或发生的非合规医疗服务、药品、耗材或时序行为。
- **示例**：`hilist_name LIKE '%宫内节育%'`、`med_list_codg = 'X'`、`det_item_fee_sumamt < 0`（退费明细）。

### 1.3 任务原型 (Audit Archetypes)
医保审计场景涵盖以下经典原型：
1. **互斥排他型 (Exclusion / Mutex)**：主体属性与项目适应症/限制属性具有生理或规则互斥（如：男用妇科/节育器/益母草，女用男科，儿童用成人专属性药物）。
2. **时序重叠型 (Temporal Overlap)**：同一主体在同一时间区间内存在物理不可能的并发事件（如：同一时间在两家异地医院住院）。
3. **频次与统计离群型 (Frequency & Outlier)**：超量开药、单笔高额离群（如 >= 1000 元）、指标远超同级医院 P95/P99 分位数。
4. **伴随依赖缺失型 (Missing Companion)**：某诊疗项目的计费必须以特定前提项目或检查结果为依据，但前提记录缺失（如：无手术记录但收取麻醉费）。
5. **负数冲正与退费型 (Reversal & Refund)**：医疗机构退费、冲正或负数计费流水的核查（`det_item_fee_sumamt < 0`），注意数量字段 `cnt` 可能为负数，绝不能误判为聚合计数。
6. **零发现基线合规型 (Zero-Findings Baseline)**：规则排查未发现任何异常数据（如同日同人同院多次结算为 0 笔），系统必须确认为合规事实，避免因 0 命中而发生无效重试与伪造数据。
7. **目录与字典核查型 (Directory & Inspection)**：定点机构等级范围、全国四级行政区划穿透、临床抗生素与西药目录核查，需路由至标准字典表而非诊疗流水大宽表。

---

## 2. 认知与防腐架构术语 (Cognitive & Guardrail Architecture)

### 2.1 认知解耦 (Cognitive Decoupling / Plan-and-Solve)
- **定义**：将大模型的推理链路在时间与角色上明确切分为两个独立阶段：
  - **意图规划阶段 (Intent Planning)**：只做业务逻辑分析，明确锁定 `AuditSubject`（谁是违规主体）、`ViolationFeature`（什么是违规行为）、`Archetype`（属于哪种逻辑类型），绝不编写具体 SQL 代码。
  - **语法合成阶段 (SQL Synthesizing / Coding)**：将已锁定的结构化意图结合数据库 Schema Registry 翻译为具体 ClickHouse 查询。

### 2.2 恒假互斥逻辑 (Contradiction Predicate)
- **定义**：布尔逻辑中的矛盾式（Contradiction），即在同一作用域内对同一属性施加了交集为空的过滤条件。
- **典型形态**：
  - 二元枚举全排除：`col NOT LIKE '1%' AND col NOT LIKE '2%'`（在二元枚举字段中导致全表排除）。
  - 同一标量等值冲突：`col = 'A' AND col = 'B'`。
  - 正反直接否定矛盾：`col = 'A' AND col != 'A'`。
  - 空值直接矛盾：`col IS NULL AND col IS NOT NULL`。
  - IN 列表与单值冲突：`col IN ('A') AND col = 'B'` (其中 B 不在 IN 列表中)。
  - 数值/日期区间倒置矛盾：`col > 1000 AND col < 100`（下限大于上限，解集为空）。
- **防腐铁律**：必须在静态 AST 语法树层由确定性规则拦截，严禁穿透到物理数据库中产生虚假空集。

### 2.3 反思自愈环 (Reflection Loop / Evaluator-Optimizer)
- **定义**：基于 Reflexion 范式的闭环质量优化机制。
- **组成**：
  - **评审员 (Critic / Evaluator)**：拥有独立于执行者的审查视角，在查询返回 0 行或触发静态警告时评估是否因主客体颠倒所致。
  - **短期记忆 (Memory)**：保存失败的 SQL 与具体的诊断反馈（Diagnostic Feedback）。
  - **自愈步进 (Refinement)**：模型依据带诊断记忆的提示词在同会话中进行一次定向纠错。

### 2.4 单一事实源枚举契约 (Single Source of Truth Enum Contract)
- 数据库字段的物理取值与业务含义必须唯一注册于 `configs/schema_registry.yaml`。
- 性别字段规范：
  - 表：`fqz_fymx_test.gend`
  - 枚举：`'1'` 代表男性（注意物理可能存在尾部制表符，推荐使用 `LIKE '1%'`），`'2'` 代表女性（推荐使用 `LIKE '2%'`）。
  - 严禁在 Prompt 提示词中随意猜测枚举，一律由 `AdaptiveSelector` 从 Schema Registry 动态装载。

### 2.5 神经符号门禁 (Neuro-Symbolic Gate)
- **定义**：将大语言模型的概率生成（Neuro / System 1）与确定性抽象语法树解析、布尔代数推导、类型系统（Symbolic / System 2）深度耦合的防御机制。
- **定位**：杜绝单纯依赖 Prompt 堆叠或 LLM-as-a-Judge 导致的不稳定性和同频幻觉，确保业务关键约束具备数学可证明的 100% 拦截率。
- **详见工程指南**：[docs/neuro_symbolic_guardrails_and_agent_engineering_guide.md](file:///f:/chain/argus-agent/docs/neuro_symbolic_guardrails_and_agent_engineering_guide.md)

