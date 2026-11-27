# AGENTS.md — Argus-Agent 仓库宪法

FastAPI + LangGraph 多智能体医保智能审计系统（`app/api` 薄控制器 → `app/orchestration` 推理流 → `app/infra` ClickHouse/Neo4j/模型路由 → `app/reporting` 渲染）。**最高风险区 = Text-to-SQL 静态 AST 安全门禁、审计原型路由（`ArchetypeRegistry`）与确定性数据对账**。

本文件是唯一权威宪法，冲突时以本文件为准；指针所指详情不在此复读。

## 一、死门禁（违反即缺陷）

1. **神经符号硬拦截**：SQL 物理执行前及经验库沉淀前，必须经过 `sqlglot` AST 安全与逻辑矛盾门禁，严禁仅靠 Prompt 自律。
2. **确定性对账铁律**：违规笔数与涉案金额必须由确定性代码直接核算底层结果行（含剥离 `UNION ALL` 汇总尾行），严禁放任大模型估算统计数字。
3. **评测基线诚信（Strict Baseline Integrity）**：Before/After 对比指标必须严格来自同源真实代码与真实测试集实跑结果，严禁倒推或编造基线；妥善保护 `scratch/verified_comprehensive_gt.json`、`scratch/v6_benchmark_result.json`、`scratch/last_5turns_result.json`。
4. **查阅优先与目录边界**：探测数据库、模型、图谱或日志统一走 `tools/dev_toolkit.py`（见 `argus-dev-tools`）；`scripts/` 仅保留标准化入口（见 `scripts/README.md`）；`scratch/` 严禁倾倒临时脚本或提交巨型日志。
5. **Windows 运行时底线**：后端必须经 `python -m app.main` 启动（内置 `WindowsSelectorEventLoopPolicy` 与 `PHOENIX_GRPC_PORT=4517` 避灾），严禁绕过启动入口。

## 二、验证命令（验收只认退出码）

> [!CAUTION]
> **切勿裸跑 `pytest`**：`pytest.ini` 默认会运行高成本 `basic`（LLM-as-judge）套件并消耗真实 Token；日常改代码先跑 `-m unit`。

| 门禁项 | 命令 | 说明 |
| :--- | :--- | :--- |
| 纯单测（零 LLM） | `pytest -m unit` | 离线单元测试与契约回归（`tests/conftest.py` 自动覆盖 `tests/unit/` 全量单测；可用 `pytest tests/unit -o "addopts="` 跳过评测目录加快收集） |
| 规则/拒答套件 | `pytest -m "rules or refusal" -o "addopts="` | 意图路由与安全拦截快速验证 |
| 静态质量审计 | `python scripts/code_quality_audit.py` | 长文件、静默异常与复杂度检查 |
| CI 门禁评测 | `python scripts/run_ci_eval.py --mode local` | 本地端到端门禁回归 |
| 工具链体检 | `python tools/dev_toolkit.py --help` | 确认 `db/model/graph/log` 统一 CLI 就绪 |

## 三、按需指针目录（Single Source of Truth）

| 文档 / Skill | 何时查阅 |
| :--- | :--- |
| `CONTEXT.md` | 修改审计逻辑、Prompt、SQL 校验或评测用例前（12 条领域定义与反模式） |
| `.agents/skills/argus-dev-tools/SKILL.md` | 探测 ClickHouse、模型算力池、Neo4j 或排查运行日志前 |
| `.agents/skills/argus-runbook/SKILL.md` | 本地启动后端/前端/ClickHouse 报错、端口冲突或代理阻塞时 |
| `scripts/README.md` | 新增运维、造数、语料或评测脚本前 |
| 全局 `llm-ops-guard` | 重构 Prompt、排查截断/思考草稿外溢、设计内部裁判或做评测复盘时 |
| 全局 `frontend-ui-guard` | 修改或排查 `html/` 监控看板及前端白屏/视口问题时 |
