# HSA 审计 Agent 企业级优化方案 (参照 hello-agents 最佳实践)

> 当前状态：系统稳定性与真实性已达到企业级（无幻觉、无假数据、无崩溃）。
> 得分瓶颈：25.2 → 49+ 分的差距完全集中在**报告专业度**与**可解释性**上。

---

## 一、问题根因矩阵

基于最新 23:29 Benchmark 数据，所有案例的共同扣分模式如下：

```
Judge 核心抱怨 (反复出现)：
1. "Lack of records of SQL/code execution" → 解释性（Interpretability）0分
2. "No description of audit logic"          → 专业度（Professionalism）0~2分
3. "No evidence of scope verification"      → 召回率（Recall）低
```

这三条诉求指向同一个核心缺陷：**报告只给结论，不给过程**。

---

## 二、企业级优化方案（借鉴 hello-agents 透明化报告模式）

### 优先级 P0：报告注入审计轨迹 (Audit Trace Injection)

**hello-agents 的做法**：在 `chapter12` 的评估体系里，每一条报告都要附带 `citations`（引用），即原始数据来源和推理链条。这是裁判最看重的"证据闭环"。

**我们的实现路径**：

#### 改动 1：`AuditState` 新增 `execution_trace` 字段

在 `app/schemas.py` 中，给 `AuditState` 增加一个字段用于汇聚执行日志：

```python
# app/schemas.py
class AuditState(TypedDict, total=False):
    # ... 现有字段 ...
    execution_trace: List[str]  # 新增：记录每一步操作的轨迹快照
```

#### 改动 2：`sqlexec_node` 和工具层把行为写入 `execution_trace`

在每次 SQL 执行或工具调用后，追加一条痕迹记录：

```python
# 在 sqlexec_node 成功执行 SQL 后：
trace = state.get("execution_trace", [])
trace.append(f"[SQL执行] 查询语句：{sql[:200]}... → 返回 {count} 条记录")
return {"raw_data": ..., "execution_trace": trace}

# 在工具层 audit_medical_rule 执行后：
trace.append(f"[规则引擎] 触发规则 {rule_id} → 命中 {count} 条证据")
```

#### 改动 3：`REPORTER_PROMPT` 注入轨迹（核心改动）

修改 `app/prompts.py` 中的 `REPORTER_PROMPT`：

```python
REPORTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一名极其严谨的审计公文拟稿人。

## 强制报告结构（必须完整包含以下所有章节）

### 一、审计任务
简述本次审计的核心目标（1-2句）。

### 二、核查口径与方法论
说明审计的依据和技术手段。示例：
- 核查口径：依据《医保基金监管条例》第X条，认定同一患者同天在两家医院住院为重叠住院。
- 检索范围：全量就诊流水表 fqz_gz_jzsj_all_ql，按 psn_no + setl_time 分组聚合。
- 判定阈值：hosp_cnt > 1 即触发违规预警。

### 三、执行轨迹（来自系统日志）
【必须】原样粘贴以下审计执行日志，不得修改：
{execution_trace}

### 四、核查结论
基于上述物理核查的真实结果，给出最终审计结论。若无违规，须写明"基于当前数据范围，未检出违规"。

### 五、风险评级
高/中/低，并说明评级依据。

## 禁令
- 如果执行轨迹为空，必须写"系统日志：本次审计未触发物理 SQL 核查，结果待确认。"
- 严禁编造任何数值。
"""),
    MessagesPlaceholder(variable_name="messages"),
    ("human", "请根据结构化数据和执行日志，撰写最终审计报告。")
])
```

---

### 优先级 P1：ClickHouse 连接稳健化

目前 QA-01（重复收费）始终得 0 分，因为 SQL 查询无法返回数据。
在 `reporter_node` 调用前，需要确认物理库中是否真的有 `fqz_gz_jzsj_all_ql` 这张表。

**诊断命令（运行前先确认）**：
```python
python -c "
from app.tools import get_clickhouse_client
c = get_clickhouse_client()
tables = c.query('SHOW TABLES')
print(tables.result_rows)
"
```

如果表不存在，QA-01 的 0 分将无解。如果存在，则需要检查 2024 年是否有数据：
```sql
SELECT count() FROM fqz_gz_jzsj_all_ql WHERE toYear(setl_time) = 2024
```

---

### 优先级 P2：丰富 `CODER_PROMPT` 的"审计口径定义"

参照 `hello-agents` 的 `chapter11` 的多轮对话模式，让模型在生成 SQL 的同时，附带一段简洁的"业务口径说明"：

**在 CODER_PROMPT 里增加：**
```
## 口径披露（强制）
每次输出 SQL 或 TOOL_CALL 后，必须追加以下 XML 标签：
<audit_rationale>
- 判定依据：[引用哪条医保法规或业务逻辑]
- 数据范围：[查询的时间段、患者群体、医院范围]
- 异常阈值：[什么条件触发违规标记]
</audit_rationale>
```

这段 `audit_rationale` 随后被 `sqlexec_node` 提取，存入 `execution_trace`，最终由 Reporter 拼接进报告，彻底解决 Professionalism 被扣分的问题。

---

## 三、预期得分提升模型

| 维度 | 当前 | 预期（实施后） | 核心改进 |
| :--- | :--- | :--- | :--- |
| **Success** | 3.2 | 6.0 | 执行轨迹使 Judge 看到了 SQL 被执行的证据 |
| **Recall** | 1.8 | 4.0 | 报告明确披露了"覆盖范围"，Judge 可验证 |
| **Precision** | 5.0 | 7.0 | 口径披露使精确性可被验证 |
| **Faithfulness** | 4.0 | 8.0 | 执行日志与结论物理绑定，无法撒谎 |
| **Relevance** | 7.5 | 8.5 | 方法论章节与任务目标强对齐 |
| **Professionalism** | 1.2 | 7.0 | 强制章节模板 + 法规引用 |
| **Interpretability** | 2.5 | 8.0 | 执行痕迹 + 证据链贴出来了 |
| **总计** | **25.2** | **≈48.5** | ⬆️ +92% |

---

## 四、实施步骤（建议顺序）

```
Step 1: 诊断 ClickHouse 数据库，确认表结构         [5 分钟]
Step 2: 在 AuditState 中加入 execution_trace 字段  [10 分钟]
Step 3: 在 sqlexec_node / 工具层写入轨迹           [15 分钟]
Step 4: 重写 REPORTER_PROMPT，注入强制报告结构      [10 分钟]
Step 5: 在 reporter_node 中将 execution_trace 格式化后注入 Prompt [5 分钟]
Step 6: 回归测试，验证得分突破 45 分               [20 分钟]
```
