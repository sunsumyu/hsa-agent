"""
app/infra/neo4j_ontology_provider.py
====================================
[Matt Pocock Deep Module] 医保审计图谱本体结构与权威提示语提供器

核心职责：
1. 维护 HSA 医保审计图谱核心节点、关系与常用 Cypher 审计模板（共享手机号、聚集性就医、高频就医）
2. 固化 Cypher 编写禁忌（禁止 SQL 关键字、禁止幻觉标签与关系）
3. 格式化图谱本体输出（Labels + Relationships + 权威提示）
"""

from __future__ import annotations

from typing import List


class Neo4jOntologyProvider:
    """医保审计图谱本体定义深模块"""

    def get_audit_graph_hints(self) -> str:
        """返回权威图谱业务模式提示词"""
        return """
## 🕸️ HSA 医保审计图谱模式 (权威定义)

### 1. 核心节点与关系
- `(p:Patient {psn_no})`: 参保人
- `(h:Hospital {fixmedins_code, name})`: 医疗机构
- `(t:Phone {tel})`: 手机号
- `(p)-[:VISITED {total_amt, count}]->(h)`: 就医关联
- `(p)-[:HAS_PHONE]->(t)`: 联系方式关联

### 2. 常用审计模式 (Cypher 模板)
- **共享手机号团伙发现**: 
  `MATCH (p1:Patient)-[:HAS_PHONE]->(t:Phone)<-[:HAS_PHONE]-(p2:Patient) WHERE p1.psn_no <> p2.psn_no RETURN p1.psn_no, p2.psn_no, t.tel`
- **聚集性就医模式**: 
  `MATCH (t:Phone {tel: $tel})<-[:HAS_PHONE]-(p:Patient)-[v:VISITED]->(h:Hospital) RETURN p.psn_no, h.name, v.total_amt`
- **高频就医人员提取**: 
  `MATCH (p:Patient)-[v:VISITED]->(h:Hospital) WHERE v.count > 10 RETURN p.psn_no, SUM(v.total_amt) AS total`

### 3. 编写禁忌 (Strictly Prohibited)
- ❌ 严禁使用 SQL 语法 (如 BETWEEN, LIKE)。
- ❌ 严禁使用不存在的标签 (如 shared_contacts, Doctor)。
- ❌ 严禁猜测关系名，必须使用 VISITED 或 HAS_PHONE。
""".strip()

    def format_ontology(self, labels: List[str], rel_types: List[str]) -> str:
        """根据数据库反射元数据拼接完整的本体说明"""
        ontology = "**[Neo4j Graph Ontology]**\n"
        ontology += f"- **Labels**: {', '.join(labels) if labels else 'None'}\n"
        ontology += f"- **Relationships**: {', '.join(rel_types) if rel_types else 'None'}\n\n"
        ontology += self.get_audit_graph_hints()
        return ontology


# 单例默认实例
neo4j_ontology_provider = Neo4jOntologyProvider()
