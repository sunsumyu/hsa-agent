"""
app/infra/field_knowledge_graph.py
==================================
[V59.3 Phase 3-B / Matt Pocock Deep Module / Facade] 字段知识图谱与医学意图扩展门面
提供确定性字段名映射、别名解析、SQL安全纠错与 Prompt 模式生成，
完全不依赖 Neo4j 物理服务。
底层解耦委托至专职深模块：
- medical_intent_lexicon (医学意图词典与扩展)
- field_alias_catalog (字段别名编目与正规化映射)
- sql_field_sanitizer (SQL 字段安全纠错与 AS 别名保护)
"""

from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from app.infra.medical_intent_lexicon import (
    MEDICAL_KNOWLEDGE_MAP,
    expand_medical_intent,
)
from app.infra.field_alias_catalog import (
    FIELD_ALIAS_REGISTRY,
    FieldAliasCatalog,
)
from app.infra.sql_field_sanitizer import SQLFieldSanitizer

__all__ = [
    "MEDICAL_KNOWLEDGE_MAP",
    "expand_medical_intent",
    "FIELD_ALIAS_REGISTRY",
    "FieldAliasCatalog",
    "SQLFieldSanitizer",
    "FieldKnowledgeGraph",
    "field_kg",
]


class FieldKnowledgeGraph:
    """
    [Phase 3-B / Matt Pocock Deep Module] 确定性字段知识图谱门面。
    为 schema_injector 和 SQLGuardian 提供确定性字段名验证和纠错能力。
    """

    def __init__(self, catalog: Optional[FieldAliasCatalog] = None):
        self._catalog = catalog or FieldAliasCatalog()
        self._sanitizer = SQLFieldSanitizer(catalog=self._catalog)
        self._registry = self._catalog.registry
        self._alias_map = self._catalog.alias_map
        self._forbidden_map = self._catalog.forbidden_map
        self._forbidden = self._catalog.forbidden_set
        logger.info(
            f"[FieldKnowledgeGraph] 已激活，注册 {len(self._registry)} 个字段映射，"
            f"{len(self._forbidden)} 个禁用别名"
        )

    def resolve(self, field_name: str) -> Optional[str]:
        """将字段名（可能是别名）解析为正规物理字段名"""
        return self._catalog.resolve(field_name)

    def is_forbidden(self, field_name: str) -> bool:
        """判断一个字段名是否是已知的错误/不存在字段"""
        return self._catalog.is_forbidden(field_name)

    def sanitize_sql(self, sql: str) -> Tuple[str, List[str]]:
        """扫描 SQL 中的禁用字段名并替换，严格保护 SELECT AS 别名"""
        return self._sanitizer.sanitize_sql(sql)

    def get_canonical_fields(self, table: Optional[str] = None) -> List[Dict[str, Any]]:
        """返回正规字段列表，可按表过滤"""
        if table:
            return [e for e in self._registry if e.get("table") == table]
        return list(self._registry)

    def format_for_prompt(self, table: Optional[str] = None, max_fields: int = 8) -> str:
        """
        生成用于 Prompt 注入的字段清单（确定性版本）。
        格式与 schema_injector.inject() 兼容，优先级更高。
        """
        entries = self.get_canonical_fields(table)[:max_fields]
        lines = [
            "**[字段知识图谱] 以下为推荐的物理映射参考。若任务涉及手机号、亲属关系、聚集性分析，请务必优先尝试调用 query_fraud_ring (图查询)：**\n"
        ]
        for e in entries:
            forbidden_hint = ""
            if e.get("forbidden_aliases"):
                forbidden_hint = f"（禁用: {', '.join(e['forbidden_aliases'][:2])}）"
            lines.append(f"- `{e['canonical']}` [{e['table']}]: {e['desc']}{forbidden_hint}")
        return "\n".join(lines)


field_kg = FieldKnowledgeGraph()
