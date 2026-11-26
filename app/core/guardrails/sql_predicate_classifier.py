"""
SQL Predicate Classifier & Normalizer Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates AST predicate traversal,
expression flattening, literal extraction, and comparable type parsing behind a clean API.
"""
import re
from typing import List, Optional, Tuple, Any
from loguru import logger
from sqlglot import exp


def flatten_and(node: exp.Expression) -> List[exp.Expression]:
    """将 AND 表达式递归扁平化，自动解开 Paren 括号"""
    if isinstance(node, exp.Paren):
        return flatten_and(node.this)
    if isinstance(node, exp.And):
        return flatten_and(node.left) + flatten_and(node.right)
    return [node]


def extract_col_name(expr: exp.Expression) -> Optional[str]:
    """从 AST 表达式中提取列名"""
    if isinstance(expr, exp.Column):
        return expr.name
    if isinstance(expr, exp.Identifier):
        return expr.this
    # 兼容例如 lower(gend) 或 trim(gend)
    if isinstance(expr, exp.Func):
        for arg in expr.args.values():
            if isinstance(arg, exp.Column):
                return arg.name
    return None


def extract_literal(expr: exp.Expression) -> Optional[str]:
    """从 AST 表达式中提取字面量值"""
    if isinstance(expr, exp.Literal):
        return str(expr.this)
    return None


def parse_comparable_value(val_obj: Any) -> Optional[float]:
    """
    解析可排序比较的值（数值 float 或 ISO 日期/时间戳）。
    """
    if val_obj is None:
        return None
    # 1. 直接 float 转换
    try:
        return float(val_obj)
    except (ValueError, TypeError) as exc:
        logger.debug(f"[SQLPredicateClassifier] Float cast skipped for {val_obj!r}: {exc}")

    # 2. ISO 日期 / 时间戳解析
    if isinstance(val_obj, str):
        clean = val_obj.strip("'\" \t\r\n")
        # 支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS 或带 T 的 ISO 格式
        match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2}))?$", clean)
        if match:
            try:
                from datetime import datetime
                date_part = match.group(1)
                time_part = match.group(2) or "00:00:00"
                dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
                return dt.timestamp()
            except (ValueError, OverflowError, OSError) as exc:
                logger.debug(f"[SQLPredicateClassifier] Date parse skipped for {clean!r}: {exc}")
    return None


_BINARY_PREDICATE_TYPES = (
    (exp.EQ, "EQ"),
    (exp.NEQ, "NEQ"),
    (exp.GT, "GT"),
    (exp.GTE, "GTE"),
    (exp.LT, "LT"),
    (exp.LTE, "LTE"),
)


def _classify_not_predicate(
    inner: exp.Expression,
    raw_repr: str,
) -> Tuple[Optional[str], Optional[str], Any, str]:
    if isinstance(inner, (exp.Like, exp.ILike)):
        col, val = extract_col_name(inner.this), extract_literal(inner.expression)
        if col and val is not None:
            return (col, "NOT_LIKE", val, raw_repr)
    elif isinstance(inner, exp.EQ):
        col, val = extract_col_name(inner.left), extract_literal(inner.right)
        if col and val is not None:
            return (col, "NEQ", val, raw_repr)
    elif isinstance(inner, exp.In):
        col = extract_col_name(inner.this)
        if col:
            vals = {extract_literal(e) for e in inner.expressions if extract_literal(e) is not None}
            return (col, "NOT_IN", vals, raw_repr)
    elif isinstance(inner, exp.Is):
        col = extract_col_name(inner.this)
        if col:
            return (col, "IS_NOT_NULL", None, raw_repr)
    return (None, None, None, raw_repr)


def classify_predicate(node: exp.Expression) -> Tuple[Optional[str], Optional[str], Any, str]:
    """
    分析单个谓词表达式。
    返回: (column_name, pred_type, normalized_value, raw_repr)
    pred_type ∈ {"EQ", "NEQ", "NOT_LIKE", "LIKE", "GT", "GTE", "LT", "LTE", "IN", "NOT_IN", "IS_NULL", "IS_NOT_NULL"}
    """
    raw_repr = node.sql()
    for expr_cls, pred_type in _BINARY_PREDICATE_TYPES:
        if isinstance(node, expr_cls):
            col, val = extract_col_name(node.left), extract_literal(node.right)
            if col and val is not None:
                return (col, pred_type, val, raw_repr)
            return (None, None, None, raw_repr)

    if isinstance(node, exp.In):
        col = extract_col_name(node.this)
        if col:
            vals = {extract_literal(e) for e in node.expressions if extract_literal(e) is not None}
            is_not = "NOT" in raw_repr.upper() or node.args.get("is_not")
            return (col, "NOT_IN" if is_not else "IN", vals, raw_repr)
    elif isinstance(node, exp.Is):
        col = extract_col_name(node.this)
        if col:
            return (col, "IS_NOT_NULL" if "NOT" in raw_repr.upper() else "IS_NULL", None, raw_repr)
    elif isinstance(node, exp.Not):
        return _classify_not_predicate(node.this, raw_repr)
    elif isinstance(node, (exp.Like, exp.ILike)):
        col, val = extract_col_name(node.this), extract_literal(node.expression)
        if col and val is not None:
            return (col, "NOT_LIKE" if "NOT" in raw_repr.upper() else "LIKE", val, raw_repr)

    return (None, None, None, raw_repr)
