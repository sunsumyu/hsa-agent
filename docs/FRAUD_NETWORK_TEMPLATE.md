# 🕸️ 欺诈网络审计：最佳实践扩展模板

本模板基于 **HSA-Agent-Python** 架构，展示了如何从单体结算审计扩展到复杂的团伙欺诈分析。

## 1. 架构迁移指南

| 模块 | HSA 单体审计 (现状) | 欺诈网络分析 (扩展) |
| :--- | :--- | :--- |
| **数据源** | 结算明细表、处方单 | 亲属关系图、共用手机号/地址、银行流水 |
| **核心工具** | SQL 过滤、OCR 识别 | **图路径搜索 (BFS/DFS)**、社群发现 |
| **Cognitive Memory** | 违规政策库 (Policy RAG) | **黑产团伙特征库 (Modus Operandi)** |
| **可视化** | 趋势图、雷达图 | **关系拓扑图 (Force-Directed Graph)** |

## 2. 核心组件示例：团伙关联探测器 (Collusion Detector)

```python
import networkx as nx
from typing import List, Dict

class FraudNetworkAnalyzer:
    """[V55.0] 欺诈团伙关系分析算子"""
    
    @staticmethod
    def detect_collusion_groups(edges: List[Dict]) -> List[List[str]]:
        """
        通过共用特征（如手机号、收货地址）发现团伙。
        edges: [{'from': 'P001', 'to': 'ADDR_123', 'type': 'lives_at'}]
        """
        G = nx.Graph()
        for edge in edges:
            G.add_edge(edge['from'], edge['to'], type=edge['type'])
        
        # 识别全连接分量（连通域即为一个潜在团伙）
        communities = list(nx.connected_components(G))
        return [list(c) for c in communities if len(c) > 2]
```

## 3. 推荐演进路线
1. **第一步：特征对撞**。利用 `app/tools.py` 增加“共用设备/手机号”的 SQL 查询。
2. **第二步：图谱建模**。将 `RichReportGenerator` 中的图谱逻辑从“证据链”升级为“利益网”。
3. **第三步：对抗演练**。利用 `scripts/evaluate_agent.py` 的 Win Rate 评估，训练模型识别隐蔽的洗钱逻辑。

---

> [!TIP]
> 您现有的 **LLM Judge** 是欺诈分析的“最后防线”。通过训练它识别“合理解释”与“刻意规避”，能有效防止对正常家庭共享行为的误判。
