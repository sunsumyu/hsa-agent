# 认知防腐与自愈闭环架构实施计划 (Cognitive Guardrails & Reflection Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use Test-Driven Development (TDD: Red-Green-Refactor) to implement this plan task-by-task.
> 
> **Explicit Constraint:** 严禁在未经过单元测试验证并获得用户批准前擅自执行全量盲测 (`benchmark_real_data.py`)！

**Goal:** 彻底攻克大模型在复杂/排斥违规场景下逻辑倒置、恒假互斥条件穿透、以及物理返回 0 行无自愈的痛点。

**Architecture:**
1. **ContradictionDetector (静态 AST 恒假矛盾拦截器)**：纯 Python + sqlglot，在 `QualityGate` 中静态阻断恒假互斥条件。
2. **AuditIntentPlanner (Plan-and-Solve 意图规划器)**：结构化解析审计主体与违规客体，彻底解耦认知推理与语法编写。
3. **AuditReflectionEngine (Reflexion 闭环自愈器)**：执行后后验评估，0 命中时提供诊断反馈，驱动自愈。

---

## Task 1: 静态 AST 恒假矛盾拦截器 — `ContradictionDetector`

**Files:**
- Create: `app/core/guardrails/contradiction_detector.py`
- Test: `tests/unit/core/test_contradiction_detector.py`
- Modify: `app/core/context/gates.py:QualityGate.validate_sql_semantics`

- [x] **Step 1: 编写红灯单元测试覆盖恒假互斥场景**
  - 测试用例 1: `gend NOT LIKE '1%' AND gend NOT LIKE '2%'` 触发拦截。
  - 测试用例 2: `gend = '1' AND gend = '2'` 触发拦截。
  - 测试用例 3: 正常 SQL（`gend LIKE '1%' AND hilist_name LIKE '%节育%'`）安全通过。
- [x] **Step 2: 实现 `ContradictionDetector` 深度模块**
  - 利用 `sqlglot` 提取 `WHERE` 谓词树。
  - 检查针对二元枚举或同一字段的互斥/全排除操作符。
- [x] **Step 3: 接入 `QualityGate.validate_sql_semantics` 并跑通单测绿灯**

---

## Task 2: 审计意图抽象规划器 — `AuditIntentPlanner`

**Files:**
- Create: `app/core/planning/audit_intent_planner.py`
- Test: `tests/unit/core/test_audit_intent_planner.py`

- [x] **Step 1: 编写红灯单元测试覆盖典型违规意图**
  - 测试用例 1: “查询男性使用宫内节育器违规明细” ➔ 锁定 `audit_subject='男性'`, `target_gender='1'`, `violation_feature='宫内节育器'`.
  - 测试用例 2: “排查女性使用前列腺增生药物” ➔ 锁定 `audit_subject='女性'`, `target_gender='2'`.
  - 测试用例 3: 常规退费场景 ➔ 识别为非性别排斥常规原型。
- [x] **Step 2: 实现 `AuditIntentPlanner`**
  - 定义标准 `AuditIntent` 与 `AuditArchetype` 枚举。
  - 提供确定性规则与快速意图解析窄接口。
- [x] **Step 3: 跑通单测绿灯**

---

## Task 3: 闭环反思自愈器 — `AuditReflectionEngine`

**Files:**
- Create: `app/core/reflection/audit_reflection_engine.py`
- Test: `tests/unit/core/test_audit_reflection_engine.py`
- Modify: `app/agents/coder_agent.py` (在质量门控阶段集成自愈诊断)

- [x] **Step 1: 编写红灯单元测试**
  - 测试用例 1: 互斥场景 + 物理返回 0 笔 ➔ 产出“请检查是否反向排除主体”诊断反馈，`needs_retry=True`。
  - 测试用例 2: 正常查出有效记录 ➔ `needs_retry=False`。
  - 测试用例 3: 捕获恒假静态异常 ➔ 产出精准矛盾点解释。
- [x] **Step 2: 实现 `AuditReflectionEngine` 深度模块**
- [x] **Step 3: 跑通单测绿灯并完成管道挂载**

---

## Task 4: 回归测试验证
- [x] 运行全套单元测试集合，确保现存 272 项单测全部保持绿灯。
- [x] 向用户汇报单元测试与架构落地成果，沉淀完整工程白皮书与上下文契约。

