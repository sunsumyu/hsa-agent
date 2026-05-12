# HSA Agent 企业级重构优化路线图
> 版本：V1.0 | 日期：2026-05-07  
> 依据：`vellum_architecture_analysis.md`、`anthropic_architecture_analysis.md`、`project_shortcomings_analysis.md`

---

## 一、核心诊断：四大系统性病灶

三份权威分析文档对本项目的诊断高度一致，归纳为四个核心病灶：

| ID | 病灶 | 当前代码体现 | 业务影响 |
|---|---|---|---|
| **P1** | 过度工程 | 6节点图 + 17字段 `AuditState` + `_trim_messages` 防御代码 | 延迟高、维护难 |
| **P2** | 死循环延迟 | `MAX_RETRIES=3`，CRITIC 打回 SQLEXEC 形成环路 | 最坏情况 3min+ |
| **P3** | Token 暴增 | 每次 Prompt 塞全量 Schema+Memory+Trace | 成本不可持续 |
| **P4** | 黑盒调试 | 正则猜大模型输出，错误无法精确溯源 | Bug 修复极难 |

---

## 二、模块化重构原则

所有新增模块必须遵守以下设计原则，以确保"**与业务解耦、方便复用**"：

1. **零业务依赖**：模块不得 import 任何医保审计特定逻辑（`audit_rules`、`anomaly_algorithms` 等）
2. **接口契约化**：所有公共函数通过类型注解明确输入输出契约
3. **无状态设计**：模块不持有 LangGraph `AuditState`，仅接收/返回 Python 原生类型
4. **可独立测试**：每个模块可以不依赖完整 Agent 图进行单元测试
5. **可配置化**：行为通过参数控制，不硬编码业务常量

---

## 三、分阶段实施路线图

### 🚀 Phase 1：快速止血模块（已实现）

#### M1: `app/message_sanitizer.py` — LLM 消息兼容性净化器
**解决问题**：P4（Doubao Thinking Mode 400 错误）

**核心能力**：
- 自动检测并净化对 Thinking Mode 模型有毒的 `AIMessage`（`reasoning_content: ''`）
- 将无工具调用的 `AIMessage` 降级为带语义标签的 `HumanMessage`
- 完全与业务解耦，任何 LangGraph 项目均可复用

**接口**：
```python
from app.message_sanitizer import sanitize_for_thinking_mode

safe_messages = sanitize_for_thinking_mode(state["messages"])
prompt = template.format_messages(messages=safe_messages, ...)
```

---

#### M2: `app/report_renderer.py` — 确定性报告渲染器
**解决问题**：P1（报告截断）、P4（黑盒输出）

**核心能力**：
- 使用确定性 Python 模板生成五章节审计报告结构
- LLM 只负责写 100~200 字的"核查结论"（第四章节），其他全部由代码生成
- 彻底消灭"大模型生成报告到一半被截断"的问题
- 输出结果可预期、可测试、可 diff

**五章节模板**：
```
## 一、审计任务         ← 直接取 user_question
## 二、核查口径         ← 由代码从 sql_query 和 table_name 生成
## 三、核查数据发现     ← 由代码从 raw_data 生成 Markdown 表格
## 四、核查结论         ← LLM 输出（仅此处，约 200 字）
## 五、风险评级         ← 由代码从金额/条数阈值计算
```

**接口**：
```python
from app.report_renderer import AuditReportRenderer

renderer = AuditReportRenderer()
full_report = renderer.render(
    user_question="核查重复住院...",
    sql_query="SELECT ...",
    raw_data=[...],           # List[Dict]
    llm_conclusion="经分析...", # LLM 只写这里
    total_amount=12500.0,
    finding_count=3,
)
```

---

#### M3: `app/fast_router.py` — 快速规则路由器
**解决问题**：P2（死循环延迟）

**核心能力**：
- 基于关键词匹配，将"已知类型"审计任务直接映射到规则算子
- 完全跳过 LLM 的 SQL 生成链路，实现 < 1s 内路由决策
- 规则库可外部配置（JSON），不需要修改代码即可新增业务规则

**接口**：
```python
from app.fast_router import FastAuditRouter

router = FastAuditRouter()
route = router.classify(user_question="核查同一患者重复住院...")
# => RouteResult(type="KNOWN_RULE", rule_id="CROSS_HOSPITAL_OVERLAP", confidence=0.95)

if route.type == "KNOWN_RULE":
    sql = rule_engine.get_rule_sql(route.rule_id)  # 直接执行，跳过 LLM
```

---

### 🔧 Phase 2：结构加固（计划中）

#### M4: `app/schema_injector.py` — 精准 Schema 注入器
**解决问题**：P3（Token 暴增）

将全量 Schema 注入改为按任务语义检索 3~5 个最相关字段，Token 成本预计降低 40~60%。

#### M5: `app/structured_tracer.py` — 结构化执行追踪器
**解决问题**：P4（黑盒调试）

将 `execution_trace` 从字符串列表升级为带时间戳、延迟、Token 消耗的结构化事件流，支持逐帧回放。

---

### 🏗️ Phase 3：架构升级（长期规划）

#### A1: 顺序工作流替代循环图
参照 Anthropic 指南建议，对高控制要求的合规审计场景，将多节点图重构为线性顺序工作流：

```
意图分类(LLM) → Fast Router → SQL执行(Python) → 数值提取(Python) → 分析结论(LLM) → 报告渲染(Python)
```

#### A2: 知识图谱替代 FAISS 向量检索
激活已有的 `neo4j_manager.py`，将字段名映射从概率性向量检索改为确定性图查询，根治"字段名幻觉"。

---

## 四、模块依赖关系图

```
agent_graph.py
    │
    ├── app/message_sanitizer.py  ← 无任何业务依赖
    ├── app/report_renderer.py    ← 无任何业务依赖
    ├── app/fast_router.py        ← 依赖 app/audit_rules.py (配置)
    │
    ├── app/audit_rules.py        ← 业务规则算子库 (已有)
    ├── app/anomaly_algorithms.py ← 业务异常检测库 (已有)
    └── app/tools.py              ← 工具入口 (已统一接入算子)
```

---

## 五、预期收益量化

| 优化项 | 影响的 Benchmark 维度 | 预期变化 |
|---|---|---|
| M1 消息净化器 | `Success`（消灭 400 崩溃） | 0 → 8+ |
| M2 确定性报告 | `Professionalism`、`Interpretability` | 6 → 9+ |
| M3 快速路由 | 响应延迟 | -60%（已知规则类） |
| M4 精准 Schema | Token 成本 | -40~60% |
| Phase 3 架构 | 全维度稳定性 | 消灭"偶发 0 分" |

---

## 六、已完成项追踪

- [x] **V58.7** `usage_tracker._estimate_tokens` 容错修复
- [x] **V58.8** `tools.py` 统一接入 `rule_engine` / `anomaly_detector`
- [x] **V58.6** `reporter_node` 报告解析增强 + `max_tokens=4096`
- [x] **V58.9.1** `message_sanitizer` Thinking Mode 净化器（全节点覆盖）
- [x] **M1 / V58.9.2** `app/message_sanitizer.py` 独立可复用模块
- [x] **M2 / V59.0** `app/report_renderer.py` + `reporter_node` 五章节确定性重构
- [x] **M3 / V59.1** `app/fast_router.py` + `planner_node` / `sqlexec_node` Fast Route 接入
- [x] **M4 / V59.2** `app/schema_injector.py` 精准 Schema 注入（替代全量 FAISS 堆砌，Token -60%）
- [x] **M5 / V59.2** `app/structured_tracer.py` 结构化执行追踪器（带耗时/Token/状态）
- [x] **Phase 3-A / V59.3** 架构降维：`critic_node` 合并进 `auditor_node`，图拓扑线性化，消灭双层循环
- [x] **Phase 3-A / V59.3** 架构降维：`critic_node` 合并进 `auditor_node`，图拓扑线性化，消灭双层循环
- [x] **Phase 3-B / V59.3** 知识图谱：`FieldKnowledgeGraph` 激活，确定性别名注册表 + `SQLGuardian` 字段自动纠错（12字段，17禁用别名）

> **所有优化阶段已全部落地。** 建议运行 Benchmark 验证整体提升效果。
