# HSA Agent 评测 Suite

## 4 个分组, 每组 5 个用例, 显式分批运行以控制 token 消耗

| Suite | 用例数 | 断言方式 | Token 成本 | 用途 |
|-------|--------|----------|------------|------|
| `basic` | 5 | DeepEval LLM-as-judge (证据链 + 数值精度) | 高 | 端到端患者行为分析回归 |
| `fuzzy` | 5 | 关键词 + SQL 模板命中 (不烧 LLM) | 低 | 模糊意图语义路由 |
| `refusal` | 5 | 关键词正则匹配 (不烧 LLM) | 极低 | SQL 注入/越权/敏感字段拦截 |
| `rules` | 5 | SQL 模板命中检查 (不烧 LLM) | 低 | 规则引擎直接激活 |

## 运行

默认只跑 `basic`（防止无意中烧掉所有配额）：

```bash
pytest tests/eval/test_agent.py
```

按 suite 分批跑：

```bash
pytest tests/eval/test_agent.py -m fuzzy
pytest tests/eval/test_agent.py -m refusal
pytest tests/eval/test_agent.py -m rules
```

全跑（生产 CI 完整回归时使用）：

```bash
pytest tests/eval/test_agent.py -m "basic or fuzzy or refusal or rules"
```

## 结果产物

每次运行在 `artifacts/eval_runs/` 下生成：

- `{timestamp}_registry.json` — 本次用到的所有 prompt `content_hash` + SQL 模板列表 + 路由规则数
- `{timestamp}_{case_id}.json` — 每个用例的 input / expected / actual / elapsed / suite / state 快照

评测得分下降时, `diff` 两次运行的 `_registry.json` 即可定位是哪个 prompt 改动导致的回归。

## 数据集文件

| 文件 | 说明 |
|------|------|
| `golden_dataset.json` | basic suite (原始 5 用例) |
| `golden_dataset_fuzzy.json` | 模糊意图路由 |
| `golden_dataset_refusal.json` | 拒绝/脱敏 |
| `golden_dataset_rules.json` | SQL 模板激活 |

## 扩充用例

每轮添加到对应 JSON 文件即可, 每个用例遵循以下字段：

```json
{
  "input": "用户自然语言输入",
  "assertion_type": "keyword_any | sql_template_used | refusal_expected",
  "expected_keywords": ["...", "..."],           // assertion_type = keyword_any / refusal_expected
  "expected_template_ids": ["GENDER_CONFLICT"],  // assertion_type = sql_template_used
  "context": "用例目的说明",
  "suite": "basic | fuzzy | refusal | rules"
}
```

**重要**: 建议每个 suite 内的用例数不超过 5 个, 避免单次回归烧光 token。新增用例先按主题分组, 超过 5 个考虑开新 suite。
