---
name: argus-dev-tools
description: 在编写任何临时脚本、探测数据库、测试模型或排查日志前必须查阅本技能。提供ClickHouse数据查询、模型连通性探测、Neo4j图谱诊断与日志排查的标准工具集(tools/dev_toolkit.py)，严禁在scratch中重复手写零散一次性脚本。
---

# Argus 统一开发与基础设施诊断工具箱 (argus-dev-tools)

## 核心原则：查阅优先 (Check-Before-Write Protocol)
> [!IMPORTANT]
> **绝对禁止在 `scratch/` 目录下盲目编写一次性的数据库连接、表结构探测、大模型调用或日志检索脚本！**
> 任何需要在开发/排查过程中查询 ClickHouse、探测模型提供商、检查 Neo4j 图数据库或分析日志的任务，**必须优先使用本项目已收敛的统一工具集**。

---

## 1. 统一工具集入口

本工具集位于 `tools/`，提供了 CLI 命令行和 Python API 两种调用方式：
- **CLI 整合入口**: `python tools/dev_toolkit.py <db|model|graph|log> <action> [args]`
- **独立命令别名**:
  - `python tools/db_tool.py <action>`
  - `python tools/model_tool.py <action>`
  - `python tools/graph_tool.py <action>`
  - `python tools/log_tool.py <action>`
- **Python 模块导入**:
  ```python
  from tools.dev_toolkit import (
      execute_sql, list_db_tables, describe_db_table, sample_db_table, count_db_table, check_db_health,
      list_available_models, test_model_call, test_tool_calling,
      check_graph_health, get_graph_stats, query_graph,
      get_recent_logs, search_log_errors
  )
  ```

---

## 2. 功能矩阵与 CLI 命令清单

### 2.1 数据库操作 (ClickHouse / 医保数据审计)
解决过去创建了几百个 `test_ck_*.py`, `check_*.py`, `dump_*.py` 的问题：

| 需求场景 | CLI 快捷命令 | 说明 |
| :--- | :--- | :--- |
| **健康检查** | `python tools/db_tool.py health` | 检测 9000/9002 (Native) 与 8123/8223 (HTTP) 端口，输出连通性与版本 |
| **列出所有表** | `python tools/db_tool.py tables` | 列出 default 库所有表名、存储引擎、行数与大小 |
| **查看表字段定义** | `python tools/db_tool.py desc <表名>` | 打印字段名、数据类型、默认值、字段注释 |
| **统计表数据行数** | `python tools/db_tool.py count <表名> [--where "条件"]` | 统计行数，支持自定义 SQL 过滤条件 |
| **采样表数据** | `python tools/db_tool.py sample <表名> -n 5` | 采样打印 5 行，支持 `--cols 字段1,字段2` 与 `--json` 输出 |
| **执行任意只读 SQL** | `python tools/db_tool.py query "SELECT ..."` | 执行 SQL（自动进行 UTF-8 编码清洗与长结果截断） |

#### 典型场景示例：
```bash
# 查看结算明细表字段
python tools/db_tool.py desc yb_fymx

# 采样某医院在特定时间段的违规候选数据
python tools/db_tool.py sample yb_fymx -n 3 --where "fixmedins_name LIKE '%医院%'"

# 执行聚合查询
python tools/db_tool.py query "SELECT med_type, count(*), sum(medfee) FROM default.yb_fymx GROUP BY med_type"
```

---

### 2.2 大模型与算力池排查 (LLM / Model Manager)
解决过去反复编写 `test_volc.py`, `probe_doubao.py`, `test_doubao_tools.py` 的问题：

| 需求场景 | CLI 快捷命令 | 说明 |
| :--- | :--- | :--- |
| **查看所有已配置模型** | `python tools/model_tool.py list` | 打印全局注册模型列表、对应厂商 (Volcengine/DashScope/Anthropic 等) |
| **测试模型连通性** | `python tools/model_tool.py test <model_id>` | 发送探测 Prompt，返回单轮推理延迟与响应内容 |
| **测试 Tool Calling** | `python tools/model_tool.py test-tools <model_id>` | 验证模型是否支持 LangChain/OpenAI 标准的函数调用能力 |

#### 典型场景示例：
```bash
# 查看算力池
python tools/model_tool.py list

# 测试 Doubao 连通性
python tools/model_tool.py test doubao-smart

# 验证 Qwen2.5 的工具调用能力
python tools/model_tool.py test-tools qwen2.5-72b-instruct
```

---

### 2.3 知识图谱诊断 (Neo4j)
解决过去编写 `test_neo4j_conn.py`, `explore_neo4j_data.py` 的问题：

| 需求场景 | CLI 快捷命令 | 说明 |
| :--- | :--- | :--- |
| **连接检查** | `python tools/graph_tool.py health` | 检测 Neo4j Aura/本地实例连接与延迟 |
| **图谱统计** | `python tools/graph_tool.py stats` | 列出所有节点标签种类 (Labels) 和关系类型 (Relationships) |
| **只读 Cypher 查询** | `python tools/graph_tool.py query "<Cypher>"` | 执行只读图谱查询并输出结构化 JSON |

---

### 2.4 日志检索与报错定位 (Logs & Traces)
解决过去编写 `parse_latest_log.py`, `extract_bench_errors.py` 的问题：

| 需求场景 | CLI 快捷命令 | 说明 |
| :--- | :--- | :--- |
| **查看最新运行日志** | `python tools/log_tool.py recent -n 50` | 打印 logs/ 目录下最新日志文件的末尾 50 行 |
| **快速定位报错** | `python tools/log_tool.py errors` | 检索日志中所有 ERROR、CRITICAL 与 Traceback 异常 |
| **关键字过滤报错** | `python tools/log_tool.py errors -k "timeout"` | 仅检索包含指定关键字的异常行 |

---

## 3. 代码内部调用方法 (Python API)

如果在编写功能模块或自动化评测时需要直接在 Python 内部复用底层能力，直接导入：

```python
from tools.dev_toolkit import execute_sql, describe_db_table, test_model_call

# 1. 安全执行只读 SQL 查询
rows = execute_sql("SELECT count(*) as total FROM default.yb_fymx")
print("Total rows:", rows[0]["total"])

# 2. 查询字段类型
columns = describe_db_table("yb_fymx")
for col in columns:
    print(col["name"], col["type"])

# 3. 验证某模型推理能力
res = test_model_call("doubao-smart", prompt="1+1=?")
assert res["status"] == "SUCCESS"
```

---

## 4. `scripts/` 标准评测、造数与语料脚本目录

在编写新的 Benchmark、造数（Seed）或语料灌入脚本前，**先查阅 [`scripts/README.md`](file:///f:/chain/argus-agent/scripts/README.md)**，严禁重复编写已被取代的旧版脚本：

| 类别 | 规范入口脚本 |
| :--- | :--- |
| **服务启停** | `scripts/start_all.ps1`、`scripts/start_clickhouse_docker.ps1` |
| **质量门禁 / 端到端基准** | `scripts/run_ci_eval.py`、`scripts/run_v6_user_perspective_benchmark.py`、`scripts/run_5_turns_7metrics_audit.py`、`scripts/run_10_turns_real_dialogue.py`、`scripts/run_adversarial_multiturn_benchmark.py` |
| **专项能力评测与静态检查** | `scripts/run_bfcl_eval.py`、`scripts/run_gaia_eval.py`、`scripts/run_legal_dialectic.py`、`scripts/benchmark_concurrency_stress.py`、`scripts/verify_comprehensive_ground_truth.py`、`scripts/code_quality_audit.py` |
| **语料构建与知识同步** | `scripts/build_official_corpus.py`、`scripts/chunk_and_ingest_corpus.py`、`scripts/ingest_expert_regulations.py`、`scripts/sync_schema.py`、`scripts/sync_to_neo4j.py` |
| **初始化与测试造数** | `scripts/init_discovery_db.py`、`scripts/init_graph_schema.py`、`scripts/seed_neo4j.py`、`scripts/seed_golden_benchmark_fixtures.py` |

---

## 5. 规范守则：关于 `scratch/` 与 `scripts/` 的管理

1. **零临时脚本原则**:
   - 如果只是查数据、查表、查模型、查日志，**100% 走 `tools/` 工具命令**，严禁在 `scratch/` 或 `scripts/` 新建 `.py`。
2. **特殊情况处理**:
   - 仅当遇到极其特殊、现成工具完全无法满足的复杂数据拟合/单次算法演练时，才允许在 `scratch/` 创建脚本；
   - 脚本命名必须具有自解释性，且任务完成后**必须主动清理或沉淀合并至 `tools/`**。
