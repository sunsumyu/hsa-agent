"""
app/skills/schema_field_pruner.py
=================================
[Matt Pocock Deep Module] Schema 字段相关性评分与 Top-K 智能剪枝引擎

核心职责：
1. 管理医保反欺诈常驻核心物理字段清单 (CORE_FIELDS)；
2. 依据用户意图词频与字段语义，执行基于长短词及描述信息熵的多级相关性评分；
3. 对大表全量字段实施截断保护，防止上百个字段产生数千 Token 开销与上下文注意力稀释。
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


DEFAULT_CORE_FIELDS: Set[str] = {
    "psn_no",
    "setl_id",
    "setl_time",
    "med_type",
    "medfee_sumamt",
    "fund_pay_sumamt",
    "fixmedins_code",
    "start_date",
    "end_date",
    "gend",
    "dise_name",
    "ipt_days",
    "psn_name",
    "brdy",
}


class SchemaFieldPruner:
    """Schema 字段相关性智能剪枝引擎"""

    def __init__(self, core_fields: Set[str] | None = None):
        self._core_fields = set(core_fields) if core_fields is not None else DEFAULT_CORE_FIELDS

    @property
    def core_fields(self) -> Set[str]:
        return self._core_fields

    def calculate_field_score(
        self,
        field_dict: Dict[str, Any],
        question_lower: str,
        question_tokens: List[str],
    ) -> int:
        """
        计算字段与用户提问的相关度评分：
        - 优先级 1（100分）：字段名直接在提问中出现；
        - 优先级 2（90分）：属于核心反欺诈主干字段；
        - 优先级 3（50分）：字段说明/中文描述包含提问关键词；
        - 优先级 4（0分）：普通冗余字段。
        """
        name = field_dict.get("field", "").lower()
        desc = field_dict.get("desc", "").lower()

        if name and name in question_lower:
            return 100

        if name in self._core_fields:
            return 90

        if question_tokens and any(kw in desc for kw in question_tokens if kw):
            return 50

        return 0

    def prune_fields(
        self,
        table_fields: List[Dict[str, Any]],
        user_question: str,
        max_fields: int = 35,
    ) -> List[Dict[str, Any]]:
        """
        对物理表的字段清单执行相关性排序与 Top-N 截断。
        当总字段数 <= max_fields 时原样返回。
        """
        if len(table_fields) <= max_fields:
            return table_fields

        q_lower = (user_question or "").lower()
        q_tokens = [tok for tok in q_lower.split() if tok]

        return sorted(
            table_fields,
            key=lambda f: self.calculate_field_score(f, q_lower, q_tokens),
            reverse=True,
        )[:max_fields]


# 单例默认实例
schema_field_pruner = SchemaFieldPruner()
