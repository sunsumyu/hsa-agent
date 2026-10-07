# 认知防腐与自愈闭环架构技术规范 (Cognitive Guardrails & Reflection Spec)

- **创建日期**：2026-10-07
- **状态**：Approved (文档驱动)
- **目标**：彻底解决大模型在复杂/互斥审计场景下主客体混淆、恒假矛盾条件放行、以及执行空集无反馈的系统性缺陷。
- **理论基石**：Matt Pocock 深模块原则（Deep Modules）+ Hello-Agents 经典范式（Plan-and-Solve & Reflection）。

---

## 1. 架构总览与分层契约

本规范新增/强化三个深度模块，均置于轻量窄接口之后，隐藏内部复杂度：

```
[用户审计请求]
      │
      ▼
┌──────────────────────────────────────────────┐
│ AuditIntentPlanner (app/core/planning)       │
│ • 窄接口: plan(prompt, context) -> Intent     │
│ • 内部隐藏: 业务主体提取、原型分类、语义互斥推导 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ CoderAgent (SQL 代码生成)                     │
│ • 基于 SchemaRegistry 动态注入契约            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ ContradictionDetector (app/core/guardrails)  │
│ • 静态 AST 深度拦截: 检测同一字段恒假矛盾     │
│ • 挂载于 QualityGate.validate_sql_semantics   │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ AuditReflectionEngine (app/core/reflection)  │
│ • 执行后后验反思: 0 命中时触发主客体诊断      │
│ • 生成结构化 DiagnosticFeedback 驱动自愈      │
└──────────────────────────────────────────────┘
```

---

## 2. 深度模块 1：静态 AST 恒假矛盾检测器 (`ContradictionDetector`)

### 2.1 模块位置
- 文件：`app/core/guardrails/contradiction_detector.py`
- 挂载点：`app/core/context/gates.py:QualityGate.validate_sql_semantics`

### 2.2 接口签名 (Narrow Interface)
```python
from typing import NamedTuple, List, Optional
import sqlglot

class ContradictionViolation(NamedTuple):
    column: str
    message: str
    conflicting_predicates: List[str]

class ContradictionDetector:
    """
    静态 AST 语义门禁：
    纯 Python + sqlglot 确定性规则，零 Token 消耗，零网络延迟。
    专注于拦截 WHERE/HAVING 条件中导致恒假空集的逻辑矛盾。
    """
    @staticmethod
    def detect(sql: str) -> Optional[ContradictionViolation]:
        ...
```

### 2.3 核心检测规则
1. **二元枚举字段全排斥 (Exhaustive NOT Exclusion)**：
   - 当同一字段（如 `gend`）在同一布尔 `AND` 作用域下，同时出现 `NOT LIKE '1%'` 和 `NOT LIKE '2%'`（或 `!= '1'` AND `!= '2'`），且该字段为已知枚举有限域时，判定为恒假矛盾。
2. **标量互斥等值 (Conflicting Equality)**：
   - 同一字段在同一 `AND` 作用域下出现 `col = 'A' AND col = 'B'` (其中 A != B)。
3. **正反直接矛盾 (Direct Negation)**：
   - 同一谓词与其自身的否定并存，如 `col = 'A' AND col != 'A'`。

---

## 3. 深度模块 2：审计意图抽象规划器 (`AuditIntentPlanner`)

### 3.1 模块位置
- 文件：`app/core/planning/audit_intent_planner.py`

### 3.2 接口签名 (Narrow Interface)
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class AuditArchetype(str, Enum):
    EXCLUSION_MUTEX = "EXCLUSION_MUTEX"          # 互斥排他
    TEMPORAL_OVERLAP = "TEMPORAL_OVERLAP"        # 时序冲突
    FREQUENCY_OUTLIER = "FREQUENCY_OUTLIER"      # 统计离群
    MISSING_COMPANION = "MISSING_COMPANION"      # 缺失伴随
    GENERAL = "GENERAL"                          # 常规查询

class AuditIntent(BaseModel):
    audit_subject: str = Field(description="违规主体 (必须正向筛选的人群/机构)")
    violation_feature: str = Field(description="客体违规特征 (诊疗项目/药品/行为)")
    archetype: AuditArchetype = Field(default=AuditArchetype.GENERAL)
    target_gender: Optional[str] = Field(default=None, description="若涉及性别冲突，明确锁定主体性别: '1'=男, '2'=女")

class AuditIntentPlanner:
    """
    将规划与代码编写解耦 (Plan-and-Solve):
    快速从问题描述与上下文分析出结构化意图，锁定审查主体。
    """
    @staticmethod
    def extract_intent(question: str) -> AuditIntent:
        ...
```

### 3.3 规则逻辑
- 针对性别专属性违规：
  - “男性使用宫内节育器/妇科” ➔ `target_gender='1'`, `violation_feature='宫内节育器'`, `archetype=EXCLUSION_MUTEX`
  - “女性使用前列腺增生药物” ➔ `target_gender='2'`, `violation_feature='前列腺'`, `archetype=EXCLUSION_MUTEX`

---

## 4. 深度模块 3：闭环反思自愈器 (`AuditReflectionEngine`)

### 4.1 模块位置
- 文件：`app/core/reflection/audit_reflection_engine.py`

### 4.2 接口签名 (Narrow Interface)
```python
from typing import Optional, Dict, Any

class ReflectionResult(BaseModel):
    needs_retry: bool
    diagnostic_feedback: Optional[str] = None
    suggested_correction: Optional[str] = None

class AuditReflectionEngine:
    """
    Reflexion 闭环自愈器 (Evaluator-Optimizer):
    在查询物理执行后或被门禁拦截时触发，生成精准的诊断反馈注入 Memory。
    """
    @staticmethod
    def evaluate_execution(
        sql: str,
        row_count: int,
        intent: Optional[AuditIntent],
        error_msg: Optional[str] = None
    ) -> ReflectionResult:
        ...
```

### 4.3 触发条件与诊断生成
1. **条件 1：恒假门禁触发**：
   - 反馈：“【静态语义门禁拦截】检测到你在字段 `{col}` 上施加了互斥恒假条件 `{predicates}`。违规主体是 `{intent.audit_subject}`，请勿同时排除该主体！”
2. **条件 2：互斥违规执行 0 行 (Zero-Hits Anomaly)**：
   - 当 `archetype == EXCLUSION_MUTEX` 且物理返回 `row_count == 0`，并且 SQL 中出现了可疑的反向过滤：
   - 反馈：“【物理执行 0 结果反思】该场景属于互斥排他审计（如男性使用女性专属性项目）。你当前的查询返回了 0 条记录，请检查是否错误地将主体反向排除了。请确保主体条件为正向过滤。”

---

## 5. 质量保证与安全防线
1. 单元测试覆盖率：三个新模块独立单测覆盖率 100%。
2. 现有测试兼容：保持现存所有测试用例绿灯通过。
3. 严格禁止未经用户允许直接启动全量盲测（`benchmark_real_data.py`）。
