# Scripts 目录资产清单与使用指南

> [!IMPORTANT]
> **新增脚本前请先核对本清单与 `tools/dev_toolkit.py`（Skill: `argus-dev-tools`）！**
> 禁止在本目录创建零散的数据库连接探测、模型探活、单次 Debug 或日志抽取脚本。

本目录仅保留经过语法与依赖校验的 **22 个核心工程入口脚本**：

## 1. 运维与启动脚本 (2 个)
- `start_all.ps1`：一键启动 Argus 全套本地服务（API、前端/守护进程等，由根目录 `start_all.bat` 调用）。
- `start_clickhouse_docker.ps1`：启动或初始化本地只读保护的 ClickHouse Docker 容器（端口 8223 / 9002）。

## 2. 语料构建与知识库同步 (5 个)
- `build_official_corpus.py`：构建权威国家医保局行政法规语料 (`official_hsa_regulations_corpus.md`)。
- `chunk_and_ingest_corpus.py`：对官方医保法典进行语义切块与向量库入库。
- `ingest_expert_regulations.py`：专家知识库（PDF/DOC/MD）全量扫描、MD5 去重与入库。
- `sync_schema.py`：从 ClickHouse 物理库全量同步表结构至真相中心 (`schema_manager`)。
- `sync_to_neo4j.py`：ClickHouse 到 Neo4j 图数据库的批量 ETL 同步流水线。

## 3. 数据库初始化与造数 (4 个)
- `init_discovery_db.py`：初始化 `data/cloud_discovery.db`（模型算力池发现库）。
- `init_graph_schema.py`：初始化 Neo4j 图谱节点唯一性约束与索引。
- `seed_golden_benchmark_fixtures.py`：向 ClickHouse 注入确定性的黄金基准测试夹具数据。
- `seed_neo4j.py`：初始化 Neo4j 字段别名本体与基础图谱结构。

## 4. 标准评测、压测与审计检查 (11 个)
- `run_ci_eval.py`：CI/CD 质量门禁评测 CLI（支持 `--mode local|cloud`、`--threshold`）。
- `run_v6_user_perspective_benchmark.py`：最新版 (V6) 真实用户视角端到端盲测基准（结果输出至 `scratch/v6_benchmark_result.json`）。
- `run_5_turns_7metrics_audit.py`：5 轮穿透式审计对话与 7 维度评估套件（结果输出至 `scratch/last_5turns_result.json`）。
- `run_10_turns_real_dialogue.py`：10 轮深度多轮对话、上下文压缩与 PII 脱敏测试。
- `run_adversarial_multiturn_benchmark.py`：5 轮极端边界与对抗性多轮会话基准实测。
- `run_bfcl_eval.py`：BFCL 工具调用能力专项评测。
- `run_gaia_eval.py`：GAIA 通用智能体能力专项评测。
- `run_legal_dialectic.py`：法律领域红蓝对抗多轮辩法交互 CLI。
- `benchmark_concurrency_stress.py`：系统级并发与幂等压力基准测试。
- `verify_comprehensive_ground_truth.py`：基于 ClickHouse 物理数据直查核对全维度用例真值（输出至 `scratch/verified_comprehensive_gt.json`）。
- `code_quality_audit.py`：静态 AST 代码质量审计（长文件、长函数、静默异常、复杂度检查）。
