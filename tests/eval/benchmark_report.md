# 记忆宫殿 (Memory Palace) 性能对比报告

生成时间: 2026-04-10 19:11:52

## 1. 核心模型得分对垒

| 模型 (Model) | 模式 (Mode) | 证据链得分 (Evidence Chain) | 数值精确度 (NP) | 平均分 | 延迟 (s) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **doubao-pro-32k** | STANDARD_RAG | 0.15 | 0.00 | **0.08** | 76.23 |
| **doubao-pro-32k** | MEMORY_PALACE | 0.65 | 0.25 | **0.45** | 113.63 |
| **gemma-4-31b-it** | STANDARD_RAG | 0.15 | 0.00 | **0.08** | 65.49 |
| **gemma-4-31b-it** | MEMORY_PALACE | 0.67 | 0.17 | **0.42** | 74.96 |
| **qwen-plus** | STANDARD_RAG | 0.20 | 0.00 | **0.10** | 58.31 |
| **qwen-plus** | MEMORY_PALACE | 0.57 | 0.25 | **0.41** | 111.17 |


## 2. 详细测试结果

| 输入 (Input) | 模型 | 模式 | 证据链 | 数值 NP | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 请分析患者 P99999 在 2026 年 1 月 15 日... | gemma-4-31b-it | STANDARD_RAG | 0.00 | 0.00 | ✅ |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | gemma-4-31b-it | STANDARD_RAG | 0.20 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | gemma-4-31b-it | STANDARD_RAG | 0.00 | 0.00 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | gemma-4-31b-it | STANDARD_RAG | 0.40 | 0.00 | ✅ |
| - | gemma-4-31b-it | STANDARD_RAG | - | - | ❌ Error: module aiohttp has no attribute ClientConnectorDNSError |
| - | gemma-4-31b-it | MEMORY_PALACE | - | - | ❌ Error: 1146 (42S02): Table 'fylqz_platform_new.policy_kb' doesn't exist |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | gemma-4-31b-it | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | gemma-4-31b-it | MEMORY_PALACE | 0.00 | 0.50 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | gemma-4-31b-it | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| - | gemma-4-31b-it | MEMORY_PALACE | - | - | ❌ Error: module aiohttp has no attribute ClientConnectorDNSError |
| - | qwen-plus | STANDARD_RAG | - | - | ❌ Error: 1146 (42S02): Table 'fylqz_platform_new.t_psn_info' doesn't exist |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | qwen-plus | STANDARD_RAG | 0.20 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | qwen-plus | STANDARD_RAG | 0.00 | 0.00 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | qwen-plus | STANDARD_RAG | 0.40 | 0.00 | ✅ |
| - | qwen-plus | STANDARD_RAG | - | - | ❌ Error: module aiohttp has no attribute ClientConnectorDNSError |
| - | qwen-plus | MEMORY_PALACE | - | - | ❌ Error: 1054 (42S22): Unknown column 'user_id' in 'where clause' |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | qwen-plus | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | qwen-plus | MEMORY_PALACE | 0.20 | 0.50 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | qwen-plus | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| 分析是否存在‘分解住院’风险？（15天内再次入院）... | qwen-plus | MEMORY_PALACE | 0.10 | 0.50 | ✅ |
| - | doubao-pro-32k | STANDARD_RAG | - | - | ❌ Error: 1146 (42S02): Table 'fylqz_platform_new.t_psn_info' doesn't exist |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | doubao-pro-32k | STANDARD_RAG | 0.20 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | doubao-pro-32k | STANDARD_RAG | 0.00 | 0.00 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | doubao-pro-32k | STANDARD_RAG | 0.40 | 0.00 | ✅ |
| 分析是否存在‘分解住院’风险？（15天内再次入院）... | doubao-pro-32k | STANDARD_RAG | 0.00 | 0.00 | ✅ |
| - | doubao-pro-32k | MEMORY_PALACE | - | - | ❌ Error: Response payload is not completed: <TransferEncodingError: 400, message='Not enough data for satisfy transfer length header.'> |
| 查询最近一年内，总医疗费用排名前三的定点医疗机构。... | doubao-pro-32k | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| 识别 2026 年 1 月份内，是否存在短时间内频繁就医（大... | doubao-pro-32k | MEMORY_PALACE | 0.20 | 0.50 | ✅ |
| 检查是否存在‘挂床住院’嫌疑的案例？（住院天数 > 15天且... | doubao-pro-32k | MEMORY_PALACE | 1.00 | 0.00 | ✅ |
| 分析是否存在‘分解住院’风险？（15天内再次入院）... | doubao-pro-32k | MEMORY_PALACE | 0.40 | 0.50 | ✅ |
