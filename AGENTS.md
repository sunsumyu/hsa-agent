# Argus-Agent 项目规范与工程守则

## 1. 基础设施探测与调试规范（严禁滥用 scratch/ 目录）
> [!IMPORTANT]
> **在编写任何数据库探测、模型调用、知识图谱诊断或日志分析脚本前，必须先查阅 Skill `argus-dev-tools` 或直接使用 `tools/dev_toolkit.py`。**

- **数据库操作 (ClickHouse)**:
  - 严禁手写 `test_ck_conn.py`、`test_ck_query.py`、`check_clickhouse_tables.py` 等一次性脚本。
  - 必须使用：
    - `python tools/db_tool.py health` (健康检查)
    - `python tools/db_tool.py tables` (查看库中所有表)
    - `python tools/db_tool.py desc <表名>` (查看表结构与字段)
    - `python tools/db_tool.py sample <表名>` (数据采样)
    - `python tools/db_tool.py query "<SQL>"` (只读 SQL 查询)
- **大模型探活与验证**:
  - 严禁手写 `test_volc.py`、`probe_doubao.py`、`test_anthropic.py`。
  - 必须使用：
    - `python tools/model_tool.py list` (查看算力池配置)
    - `python tools/model_tool.py test <model_id>` (探活与推理测试)
    - `python tools/model_tool.py test-tools <model_id>` (Tool Calling 工具调用验证)
- **知识图谱 (Neo4j)**:
  - 必须使用：`python tools/graph_tool.py health` / `stats` / `query`
- **日志排查**:
  - 必须使用：`python tools/log_tool.py recent` / `errors`

## 2. scratch/ 与 scripts/ 目录管理守则
- `scratch/` 目录严禁作为垃圾场倾倒日志与临时查询脚本；
- `scripts/` 目录仅保留标准化的运维、造数、语料灌入与基准评测入口（完整清单见 `scripts/README.md`）。严禁向 `scripts/` 写入临时 Debug、探活或一次性验证脚本（此类需求统一使用 `tools/dev_toolkit.py`）；
- 评测固化的基准真值与结果矩阵文件（如 `verified_comprehensive_gt.json`、`v6_benchmark_result.json`）需妥善保护；
- 严禁提交巨型文本、日志 Dump（如 `searched_logs.txt` 等）至版本控制。
