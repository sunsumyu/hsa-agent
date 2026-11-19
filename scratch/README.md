# Scratch 临时目录说明与规范

## ⚠️ 严禁在此创建重复的探测脚本！

在过去的开发历史中，本目录曾被随意创建了超过 500 个零散的一次性测试脚本（如 `test_ck_*.py`、`check_*.py`、`probe_*.py` 等），造成极大的工程混乱和垃圾倾倒。

### 【强制规范】
1. **优先使用统一工具箱**:
   所有关于 ClickHouse 数据库操作、模型连通性探活、Neo4j 图谱诊断及日志分析，**必须使用 `tools/dev_toolkit.py`**（或快捷命令 `tools/db_tool.py`, `tools/model_tool.py`, `tools/graph_tool.py`, `tools/log_tool.py`）。
   详情请查阅项目 Skill: `argus-dev-tools`。
2. **禁止提交巨型日志**:
   禁止在本目录倾倒超过 100KB 的纯文本日志或查询 Dump。
3. **保留文件说明**:
   本目录下目前保留的 `.json` 属于基准评测（Benchmark）的真值固化矩阵（如 `verified_comprehensive_gt.json`、`v6_benchmark_result.json`），请勿随意删除。
