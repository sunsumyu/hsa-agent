from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple
import sqlglot
from sqlglot import exp
from loguru import logger

from app.core.guardrails.sql_predicate_classifier import (
    flatten_and as _flatten_and,
    classify_predicate as _classify_predicate,
    extract_col_name as _extract_col_name,
    extract_literal as _extract_literal,
    parse_comparable_value as _parse_comparable_value,
)


class ContradictionViolation(NamedTuple):
    column: str
    message: str
    conflicting_predicates: List[str]


@dataclass
class _ScopePredicates:
    equalities: Dict[str, Set[str]] = field(default_factory=dict)
    inequalities: Dict[str, Set[str]] = field(default_factory=dict)
    likes: Dict[str, Set[str]] = field(default_factory=dict)
    not_likes: Dict[str, Set[str]] = field(default_factory=dict)
    in_lists: Dict[str, Set[str]] = field(default_factory=dict)
    not_in_lists: Dict[str, Set[str]] = field(default_factory=dict)
    is_null: Set[str] = field(default_factory=set)
    is_not_null: Set[str] = field(default_factory=set)
    lower_bounds: Dict[str, List[Tuple[float, bool]]] = field(default_factory=dict)
    upper_bounds: Dict[str, List[Tuple[float, bool]]] = field(default_factory=dict)
    raw_predicates: Dict[str, List[str]] = field(default_factory=dict)


class ContradictionDetector:
    """
    [Deep Module] 静态 AST 语义恒假互斥拦截器。

    采用纯 Python + sqlglot 确定性规则，运行于 SQL 物理执行前。
    专注于截杀在同一 AND 作用域下对同一属性施加的导致恒假空集的逻辑矛盾。
    """

    KNOWN_BINARY_ENUMS = {
        "gend": {"1", "2"},
        "gender": {"1", "2"},
    }

    @classmethod
    def detect(cls, sql: str, archetypes: Optional[List[Any]] = None) -> Optional[ContradictionViolation]:
        """静态检测 SQL 中是否存在导致恒假空集的逻辑矛盾或违反领域任务原型的不变式。"""
        if not sql or not sql.strip():
            return None

        clean_sql = sql.replace('\\n', '\n').strip().rstrip(';； \n\r\t')
        try:
            parsed = sqlglot.parse_one(clean_sql, read="clickhouse")
        except Exception as e:
            logger.debug(f"[ContradictionDetector] sqlglot 解析跳过 (非关键语法): {e}")
            return None
        if not parsed:
            return None

        has_cross_row = (
            bool(parsed.find(exp.Join))
            or len(list(parsed.find_all(exp.Select))) > 1
            or bool(parsed.find(exp.Subquery))
            or bool(parsed.find(exp.Window))
            or (bool(parsed.find(exp.Group)) and bool(parsed.find(exp.Having)))
        )

        for clause in parsed.find_all(exp.Where, exp.Having):
            violation = cls._check_scope(clause.this, has_cross_row=has_cross_row, archetypes=archetypes)
            if violation:
                return violation
        return None

    @classmethod
    def _collect_scope_predicates(cls, and_conjuncts: List[exp.Expression]) -> _ScopePredicates:
        preds = _ScopePredicates()
        for node in and_conjuncts:
            col_name, pred_type, val_obj, raw_repr = cls._classify_predicate(node)
            if not col_name:
                continue
            col = col_name.lower()
            preds.raw_predicates.setdefault(col, []).append(raw_repr)
            if pred_type == "EQ":
                preds.equalities.setdefault(col, set()).add(val_obj)
            elif pred_type == "NEQ":
                preds.inequalities.setdefault(col, set()).add(val_obj)
            elif pred_type == "LIKE":
                preds.likes.setdefault(col, set()).add(val_obj)
            elif pred_type == "NOT_LIKE":
                preds.not_likes.setdefault(col, set()).add(val_obj.rstrip("%"))
            elif pred_type == "IN" and isinstance(val_obj, set):
                preds.in_lists.setdefault(col, set()).update(val_obj)
            elif pred_type == "NOT_IN" and isinstance(val_obj, set):
                preds.not_in_lists.setdefault(col, set()).update(val_obj)
            elif pred_type == "IS_NULL":
                preds.is_null.add(col)
            elif pred_type == "IS_NOT_NULL":
                preds.is_not_null.add(col)
            elif pred_type in ("GT", "GTE"):
                c_val = cls._parse_comparable_value(val_obj)
                if c_val is not None:
                    preds.lower_bounds.setdefault(col, []).append((c_val, pred_type == "GT"))
            elif pred_type in ("LT", "LTE"):
                c_val = cls._parse_comparable_value(val_obj)
                if c_val is not None:
                    preds.upper_bounds.setdefault(col, []).append((c_val, pred_type == "LT"))
        return preds

    @classmethod
    def _check_core_equality_conflicts(cls, p: _ScopePredicates) -> Optional[ContradictionViolation]:
        for col, eq_vals in p.equalities.items():
            if len(eq_vals) > 1:
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 在同一 AND 作用域下被同时要求等于不同的值 {sorted(list(eq_vals))}，产生恒假矛盾！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
            overlap = eq_vals.intersection(p.inequalities.get(col, set()))
            if overlap:
                val = next(iter(overlap))
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 存在正反直接矛盾 (`= '{val}'` 与 `!= '{val}'`)，导致逻辑恒假！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        null_conflicts = p.is_null.intersection(p.is_not_null)
        if null_conflicts:
            col = next(iter(null_conflicts))
            return ContradictionViolation(
                column=col,
                message=f"字段 `{col}` 存在空值直接矛盾 (同时要求 IS NULL 与 IS NOT NULL)，导致逻辑恒假！",
                conflicting_predicates=p.raw_predicates.get(col, []),
            )
        for col, in_vals in p.in_lists.items():
            if col in p.equalities and not in_vals.intersection(p.equalities[col]):
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 要求等于 {sorted(list(p.equalities[col]))}，但在 IN 允许集合 {sorted(list(in_vals))} 中不存在，产生恒假矛盾！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        return None

    @classmethod
    def _check_enum_and_bound_conflicts(cls, p: _ScopePredicates) -> Optional[ContradictionViolation]:
        for col, known_vals in cls.KNOWN_BINARY_ENUMS.items():
            excluded_vals = set(p.not_likes.get(col, set())) | set(p.inequalities.get(col, set()))
            if known_vals.issubset(excluded_vals):
                return ContradictionViolation(
                    column=col,
                    message=(
                        f"字段 `{col}` 是二元枚举属性 (合法取值为 {sorted(list(known_vals))})，"
                        f"但在查询中同时排除了所有取值 {sorted(list(excluded_vals))}，"
                        "导致恒假空集 (全表记录被 100% 过滤)！"
                    ),
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        for col, lower_list in p.lower_bounds.items():
            if col not in p.upper_bounds:
                continue
            max_lower = max(lower_list, key=lambda x: x[0])
            min_upper = min(p.upper_bounds[col], key=lambda x: x[0])
            if max_lower[0] > min_upper[0]:
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 存在数值/时间区间倒置矛盾 (要求下限大于上限)，导致恒假空集！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
            if max_lower[0] == min_upper[0] and (max_lower[1] or min_upper[1]):
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 存在严格区间重叠矛盾 (下限等于上限且包含严格不等式)，无任何数值满足！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        return cls._check_equality_bound_conflicts(p)

    @classmethod
    def _check_equality_bound_conflicts(cls, p: _ScopePredicates) -> Optional[ContradictionViolation]:
        for col, eq_vals in p.equalities.items():
            for eq_raw in eq_vals:
                c_eq = cls._parse_comparable_value(eq_raw)
                if c_eq is None:
                    continue
                for lower_val, is_strict in p.lower_bounds.get(col, ()):
                    if c_eq < lower_val or (c_eq == lower_val and is_strict):
                        return ContradictionViolation(
                            column=col,
                            message=f"字段 `{col}` 等值设定为 '{eq_raw}'，但同时被要求下限 >{'=' if not is_strict else ''} 冲突界限，产生恒假矛盾！",
                            conflicting_predicates=p.raw_predicates.get(col, []),
                        )
                for upper_val, is_strict in p.upper_bounds.get(col, ()):
                    if c_eq > upper_val or (c_eq == upper_val and is_strict):
                        return ContradictionViolation(
                            column=col,
                            message=f"字段 `{col}` 等值设定为 '{eq_raw}'，但同时被要求上限 <{'=' if not is_strict else ''} 冲突界限，产生恒假矛盾！",
                            conflicting_predicates=p.raw_predicates.get(col, []),
                        )
        return None

    @classmethod
    def _check_set_exclusion_conflicts(cls, p: _ScopePredicates) -> Optional[ContradictionViolation]:
        for col, eq_vals in p.equalities.items():
            conflict = eq_vals.intersection(p.not_in_lists.get(col, set()))
            if conflict:
                val = next(iter(conflict))
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 要求等于 '{val}'，但同时出现在 NOT IN 排除列表中，产生恒假矛盾！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        for col, in_vals in p.in_lists.items():
            if col in p.not_in_lists and in_vals.issubset(p.not_in_lists[col]):
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 的 IN 允许列表 {sorted(list(in_vals))} 已被 NOT IN 排除列表完全排除，导致恒假空集！",
                    conflicting_predicates=p.raw_predicates.get(col, []),
                )
        return None

    @classmethod
    def _check_archetype_antipatterns(
        cls,
        p: _ScopePredicates,
        archetypes: Optional[List[Any]],
        has_cross_row: bool,
    ) -> Optional[ContradictionViolation]:
        if not archetypes or has_cross_row:
            return None
        arch_cat_strs = {str(getattr(getattr(a, "category", a), "value", getattr(a, "category", a))) for a in archetypes}
        target_cols = ("hilist_name", "item_name", "med_list_codg", "hilist_code")
        if "missing_companion" in arch_cat_strs:
            for col in target_cols:
                if col in p.not_likes or col in p.inequalities:
                    return ContradictionViolation(
                        column=col,
                        message=(
                            "【伴随依赖缺失审计拦截】检测到单行伪排除反模式！"
                            "排查“无前置项目收取伴随项目”（如无手术收麻醉费）必须在就诊/结算粒度（如 `setl_id`）"
                            "通过子查询（`NOT IN (SELECT setl_id FROM ... WHERE hilist_name LIKE '%手术%')`）、"
                            "`LEFT JOIN ... IS NULL` 或窗口聚合进行跨行核对，"
                            f"严禁在单条明细记录的 WHERE 子句中直接施加伴随字段的否定排除（如 {col} NOT LIKE），"
                            "否则将导致所有伴随明细全量误判为违规！"
                        ),
                        conflicting_predicates=p.raw_predicates.get(col, []),
                    )
        if "split_billing" in arch_cat_strs:
            for col in target_cols:
                if len(p.likes.get(col, set())) >= 2:
                    return ContradictionViolation(
                        column=col,
                        message=(
                            f"【分解收费审计拦截】检测到同一单条明细记录上对项目字段 ({col}) 施加了多个互斥的 LIKE 匹配！"
                            "单条流水记录的品名不可能同时包含不同手术/步骤名称。"
                            "排查主干手术与子步骤分解收费，必须在就诊粒度（setl_id / mdtrt_id）通过自连接 JOIN、"
                            f"子查询或 GROUP BY setl_id 统计项目种类，严禁在单条明细的 WHERE 中同时匹配多个项目！"
                        ),
                        conflicting_predicates=p.raw_predicates.get(col, []),
                    )
        return None

    @classmethod
    def _check_scope(
        cls,
        root_node: exp.Expression,
        has_cross_row: bool = False,
        archetypes: Optional[List[Any]] = None,
    ) -> Optional[ContradictionViolation]:
        """提取 AND 连接的作用域，并分析各列上的谓词集合。"""
        if not root_node:
            return None
        and_conjuncts = cls._flatten_and(root_node)
        if len(and_conjuncts) < 1 or (len(and_conjuncts) < 2 and not archetypes):
            return None

        predicates = cls._collect_scope_predicates(and_conjuncts)
        return (
            cls._check_core_equality_conflicts(predicates)
            or cls._check_enum_and_bound_conflicts(predicates)
            or cls._check_set_exclusion_conflicts(predicates)
            or cls._check_archetype_antipatterns(predicates, archetypes, has_cross_row)
        )

    @classmethod
    def _flatten_and(cls, node: exp.Expression) -> List[exp.Expression]:
        """将 AND 表达式递归扁平化，委托至 sql_predicate_classifier"""
        return _flatten_and(node)

    @classmethod
    def _classify_predicate(cls, node: exp.Expression) -> Tuple[Optional[str], Optional[str], Any, str]:
        """分析单个谓词表达式，委托至 sql_predicate_classifier"""
        return _classify_predicate(node)

    @classmethod
    def _extract_col_name(cls, expr: exp.Expression) -> Optional[str]:
        """提取列名，委托至 sql_predicate_classifier"""
        return _extract_col_name(expr)

    @classmethod
    def _extract_literal(cls, expr: exp.Expression) -> Optional[str]:
        """提取字面量，委托至 sql_predicate_classifier"""
        return _extract_literal(expr)

    @classmethod
    def _parse_comparable_value(cls, val_obj: Any) -> Optional[float]:
        """解析可比较值，委托至 sql_predicate_classifier"""
        return _parse_comparable_value(val_obj)
