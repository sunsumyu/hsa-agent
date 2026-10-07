# 认知防腐与自愈闭环 Phase 2 实施计划 (Cognitive Guardrails Phase 2 Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use Test-Driven Development (TDD: Red-Green-Refactor) to implement this plan task-by-task.
> 
> **Explicit User Constraint:** 严禁在未获得用户明确指令前擅自执行全量盲测 (`benchmark_real_data.py`)！遵循深模块原则与文档/测试驱动开发。

**Goal:** 将神经符号防腐体系从单点性别互斥扩展至医保审计全原型（涵盖 QA-SCOPE-01 到 QA-SCOPE-10），强化数值区间/空值/集合等 AST 形式化矛盾拦截，解耦负数退费、零发现基线合规与字典穿透，构建多原型自愈闭环。

**Architecture Alignment:**
1. **ContradictionDetector (AST 符号门禁深化)**：
   - 新增数值区间倒置矛盾拦截（如 `col > 1000 AND col < 100`、时序倒置）。
   - 新增空值直接矛盾拦截（`col IS NULL AND col IS NOT NULL`）。
   - 新增集合全排斥与成员直接矛盾拦截（`col IN ('A') AND col NOT IN ('A')`）。
2. **AuditIntentPlanner (意图规划全原型覆盖)**：
   - 扩充 `AuditArchetype` 枚举：`REVERSAL_REFUND` (负数冲正), `ZERO_FINDINGS_BASELINE` (零发现基线), `DIRECTORY_INSPECTION` (字典/机构资质)。
   - 丰富临床药品知识库：涵盖益母草、地屈孕酮、雌二醇、黄体酮等女性专属药，无缝赋能 QA-SCOPE-01。
   - 注入强约束指导：针对退费场景锁定 `det_item_fee_sumamt < 0` 且防范混淆 `cnt` 与 `count(*)`。
3. **AuditReflectionEngine (多原型自愈对账)**：
   - 针对 `REVERSAL_REFUND`，若执行 0 笔则诊断是否漏写负数或误用绝对值。
   - 针对 `ZERO_FINDINGS_BASELINE`，明确放行合规零发现，禁止无效死循环与幻觉。
4. **权威单一事实源更新**：同步更新 `CONTEXT.md` 契约。

---

## Task 1: 符号门禁深化 — `ContradictionDetector` 数值区间/空值/集合矛盾拦截

**Files:**
- Modify: `tests/unit/test_contradiction_detector.py`
- Modify: `app/core/guardrails/contradiction_detector.py`

- [x] **Step 1: 编写红灯单元测试**
  - 测试用例：数值区间矛盾 `det_item_fee_sumamt > 1000 AND det_item_fee_sumamt < 100`。
  - 测试用例：空值矛盾 `psn_no IS NULL AND psn_no IS NOT NULL`。
  - 测试用例：集合与等值冲突 `gend IN ('1') AND gend = '2'`。
- [x] **Step 2: 实现 AST 符号推导算法**
  - 提取 `exp.GT`, `exp.GTE`, `exp.LT`, `exp.LTE` 并针对同一数值列推导区间有效性 $[low, high]$，当 $low > high$ 时拦截。
  - 提取 `exp.Is` 与 `exp.Not(exp.Is)` 检测 NULL 冲突。
- [x] **Step 3: 运行测试并验证绿灯**

---

## Task 2: 意图规划全原型覆盖 — `AuditIntentPlanner`

**Files:**
- Modify: `tests/unit/test_audit_intent_planner.py`
- Modify: `app/core/planning/audit_intent_planner.py`

- [x] **Step 1: 编写红灯单元测试**
  - 测试用例 1: QA-SCOPE-01 男性开具益母草颗粒/地屈孕酮片 -> 锁定男性主体与妇科专属药品。
  - 测试用例 2: QA-SCOPE-03 负数退费与冲正核查 -> 识别 `REVERSAL_REFUND` 原型并锁定负数约束。
  - 测试用例 3: QA-SCOPE-06 同日同人同院重复结算排查 -> 识别 `ZERO_FINDINGS_BASELINE` 原型。
  - 测试用例 4: QA-SCOPE-07/08/09 定点医药机构库与行政区划核查 -> 识别 `DIRECTORY_INSPECTION` 原型。
- [x] **Step 2: 扩充原型枚举与提取规则**
  - 扩展 `AuditArchetype`。
  - 完善专属性药品字典与退费/基线/字典语义提取。
- [x] **Step 3: 运行测试并验证绿灯**

---

## Task 3: 多原型自愈反思器深化 — `AuditReflectionEngine`

**Files:**
- Modify: `tests/unit/test_audit_reflection_engine.py`
- Modify: `app/core/reflection/audit_reflection_engine.py`

- [x] **Step 1: 编写红灯单元测试**
  - 测试用例 1: 退费原型执行 0 行且 SQL 包含正数或缺少 `< 0` -> 触发自愈诊断。
  - 测试用例 2: 零发现基线场景执行 0 行 -> 正常合规放行，`needs_retry=False`，防止死循环。
- [x] **Step 2: 实现反思器多原型对账逻辑**
- [x] **Step 3: 运行测试并验证绿灯**

---

## Task 4: 单一事实源同步与全仓回归测试

**Files:**
- Modify: `CONTEXT.md`

- [x] **Step 1: 同步更新 `CONTEXT.md` 中的领域原型与契约**
- [x] **Step 2: 运行全仓单元测试，确保现存 282+ 测试 100% 绿灯**
- [x] **Step 3: 严守安全约束，向用户交付阶段成果与技术复盘**
