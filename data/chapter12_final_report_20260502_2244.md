# 🏆 HSA 审计智能体工业级评测报告 (Chapter 12 Standard)
- **评测时间**: 2026-05-02 22:44:32.496357
- **裁判模型**: models/gemini-1.5-flash-latest

| 案例 ID | 技术标签 | 专家评分 (满分 30) | 响应耗时 | 专家建议 |
| :--- | :--- | :--- | :--- | :--- |
| QA-01 | SQL_PRECISION | **0** | N/A | 崩溃报错: Recursion limit of 50 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/GRAPH_RECURSION_LIMIT |
| QA-03 | BUSINESS_LOGIC | **0** | 120.8s | 裁判由于 API 压力未给出评分: 'list' object has no attribute 'replace' |
| QA-04 | MULTIMODAL_VISION | **0** | 115.2s | 裁判由于 API 压力未给出评分: 'list' object has no attribute 'replace' |
| QA-06 | COMPLEX_JOIN | **0** | N/A | 崩溃报错: Recursion limit of 50 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/GRAPH_RECURSION_LIMIT |
| QA-11 | FRAUD_NETWORK | **0** | N/A | 崩溃报错: Error code: 403 - {'error': {'message': 'The free tier of the model has been exhausted. If you wish to continue access the model on a paid basis, please disable the "use free tier only" mode in the management console.', 'type': 'AllocationQuota.FreeTierOnly', 'param': None, 'code': 'AllocationQuota.FreeTierOnly'}, 'id': 'chatcmpl-6335e51d-3342-9bfc-8cd8-eec8176b2f5f', 'request_id': '6335e51d-3342-9bfc-8cd8-eec8176b2f5f'} |