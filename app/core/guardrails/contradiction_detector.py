import re
from typing import NamedTuple, List, Optional, Dict, Set, Tuple, Any
import sqlglot
from sqlglot import exp
from loguru import logger

class ContradictionViolation(NamedTuple):
    column: str
    message: str
    conflicting_predicates: List[str]

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
    def detect(cls, sql: str) -> Optional[ContradictionViolation]:
        """
        静态检测 SQL 中是否存在导致恒假空集的逻辑矛盾。
        若发现矛盾，返回 ContradictionViolation；若合规，返回 None。
        """
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

        # 遍历所有 WHERE 和 HAVING 子句
        for clause in parsed.find_all(exp.Where, exp.Having):
            violation = cls._check_scope(clause.this)
            if violation:
                return violation

        return None

    @classmethod
    def _check_scope(cls, root_node: exp.Expression) -> Optional[ContradictionViolation]:
        """
        提取 AND 连接的作用域，并分析各列上的谓词集合。
        """
        if not root_node:
            return None

        # 扁平化顶层 AND 节点
        and_conjuncts = cls._flatten_and(root_node)
        if len(and_conjuncts) < 2:
            return None

        # 按字段名归类谓词
        col_equalities: Dict[str, Set[str]] = {}
        col_inequalities: Dict[str, Set[str]] = {}
        col_not_likes: Dict[str, Set[str]] = {}
        col_in_lists: Dict[str, Set[str]] = {}
        col_not_in_lists: Dict[str, Set[str]] = {}
        col_is_null: Set[str] = set()
        col_is_not_null: Set[str] = set()
        col_lower_bounds: Dict[str, List[Tuple[float, bool]]] = {}
        col_upper_bounds: Dict[str, List[Tuple[float, bool]]] = {}
        col_raw_predicates: Dict[str, List[str]] = {}

        for node in and_conjuncts:
            col_name, pred_type, val_obj, raw_repr = cls._classify_predicate(node)
            if not col_name:
                continue

            col_name_lower = col_name.lower()
            col_raw_predicates.setdefault(col_name_lower, []).append(raw_repr)

            if pred_type == "EQ":
                col_equalities.setdefault(col_name_lower, set()).add(val_obj)
            elif pred_type == "NEQ":
                col_inequalities.setdefault(col_name_lower, set()).add(val_obj)
            elif pred_type == "NOT_LIKE":
                base_val = val_obj.rstrip("%")
                col_not_likes.setdefault(col_name_lower, set()).add(base_val)
            elif pred_type == "IN" and isinstance(val_obj, set):
                col_in_lists.setdefault(col_name_lower, set()).update(val_obj)
            elif pred_type == "NOT_IN" and isinstance(val_obj, set):
                col_not_in_lists.setdefault(col_name_lower, set()).update(val_obj)
            elif pred_type == "IS_NULL":
                col_is_null.add(col_name_lower)
            elif pred_type == "IS_NOT_NULL":
                col_is_not_null.add(col_name_lower)
            elif pred_type in ("GT", "GTE"):
                c_val = cls._parse_comparable_value(val_obj)
                if c_val is not None:
                    is_strict = (pred_type == "GT")
                    col_lower_bounds.setdefault(col_name_lower, []).append((c_val, is_strict))
            elif pred_type in ("LT", "LTE"):
                c_val = cls._parse_comparable_value(val_obj)
                if c_val is not None:
                    is_strict = (pred_type == "LT")
                    col_upper_bounds.setdefault(col_name_lower, []).append((c_val, is_strict))

        # 1. 检查标量互斥等值: col = '1' AND col = '2'
        for col, eq_vals in col_equalities.items():
            if len(eq_vals) > 1:
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 在同一 AND 作用域下被同时要求等于不同的值 {sorted(list(eq_vals))}，产生恒假矛盾！",
                    conflicting_predicates=col_raw_predicates.get(col, [])
                )

        # 2. 检查正反直接否定: col = '1' AND col != '1'
        for col, eq_vals in col_equalities.items():
            neq_vals = col_inequalities.get(col, set())
            overlap = eq_vals.intersection(neq_vals)
            if overlap:
                val = next(iter(overlap))
                return ContradictionViolation(
                    column=col,
                    message=f"字段 `{col}` 存在正反直接矛盾 (`= '{val}'` 与 `!= '{val}'`)，导致逻辑恒假！",
                    conflicting_predicates=col_raw_predicates.get(col, [])
                )

        # 3. 检查空值冲突: col IS NULL AND col IS NOT NULL
        null_conflicts = col_is_null.intersection(col_is_not_null)
        if null_conflicts:
            col = next(iter(null_conflicts))
            return ContradictionViolation(
                column=col,
                message=f"字段 `{col}` 存在空值直接矛盾 (同时要求 IS NULL 与 IS NOT NULL)，导致逻辑恒假！",
                conflicting_predicates=col_raw_predicates.get(col, [])
            )

        # 4. 检查 IN 集合与标量等值冲突: col IN ('1') AND col = '2'
        for col, in_vals in col_in_lists.items():
            if col in col_equalities:
                eq_vals = col_equalities[col]
                if not in_vals.intersection(eq_vals):
                    return ContradictionViolation(
                        column=col,
                        message=f"字段 `{col}` 要求等于 {sorted(list(eq_vals))}，但在 IN 允许集合 {sorted(list(in_vals))} 中不存在，产生恒假矛盾！",
                        conflicting_predicates=col_raw_predicates.get(col, [])
                    )

        # 5. 检查二元枚举字段全排斥: gend NOT LIKE '1%' AND gend NOT LIKE '2%' (或 != '1' AND != '2')
        for col, known_vals in cls.KNOWN_BINARY_ENUMS.items():
            excluded_vals = set()
            if col in col_not_likes:
                excluded_vals.update(col_not_likes[col])
            if col in col_inequalities:
                excluded_vals.update(col_inequalities[col])

            # 如果对已知二元枚举的所有合法取值都进行了排除
            if known_vals.issubset(excluded_vals):
                return ContradictionViolation(
                    column=col,
                    message=(
                        f"字段 `{col}` 是二元枚举属性 (合法取值为 {sorted(list(known_vals))})，"
                        f"但在查询中同时排除了所有取值 {sorted(list(excluded_vals))}，"
                        f"导致恒假空集 (全表记录被 100% 过滤)！"
                    ),
                    conflicting_predicates=col_raw_predicates.get(col, [])
                )

        # 6. 检查数值区间倒置矛盾: col > 1000 AND col < 100
        for col, lower_list in col_lower_bounds.items():
            if col in col_upper_bounds:
                upper_list = col_upper_bounds[col]
                max_lower = max(lower_list, key=lambda x: x[0])
                min_upper = min(upper_list, key=lambda x: x[0])

                if max_lower[0] > min_upper[0]:
                    return ContradictionViolation(
                        column=col,
                        message=f"字段 `{col}` 存在数值/时间区间倒置矛盾 (要求下限大于上限)，导致恒假空集！",
                        conflicting_predicates=col_raw_predicates.get(col, [])
                    )
                elif max_lower[0] == min_upper[0] and (max_lower[1] or min_upper[1]):
                    return ContradictionViolation(
                        column=col,
                        message=f"字段 `{col}` 存在严格区间重叠矛盾 (下限等于上限且包含严格不等式)，无任何数值满足！",
                        conflicting_predicates=col_raw_predicates.get(col, [])
                    )

        # 7. 检查等值与区间边界矛盾: col = 10 AND col > 18, 或 setl_time = '2024-01-01' AND setl_time > '2024-06-01'
        for col, eq_vals in col_equalities.items():
            for eq_raw in eq_vals:
                c_eq = cls._parse_comparable_value(eq_raw)
                if c_eq is None:
                    continue
                if col in col_lower_bounds:
                    for (lower_val, is_strict) in col_lower_bounds[col]:
                        if c_eq < lower_val or (c_eq == lower_val and is_strict):
                            return ContradictionViolation(
                                column=col,
                                message=f"字段 `{col}` 等值设定为 '{eq_raw}'，但同时被要求下限 >{'=' if not is_strict else ''} 冲突界限，产生恒假矛盾！",
                                conflicting_predicates=col_raw_predicates.get(col, [])
                            )
                if col in col_upper_bounds:
                    for (upper_val, is_strict) in col_upper_bounds[col]:
                        if c_eq > upper_val or (c_eq == upper_val and is_strict):
                            return ContradictionViolation(
                                column=col,
                                message=f"字段 `{col}` 等值设定为 '{eq_raw}'，但同时被要求上限 <{'=' if not is_strict else ''} 冲突界限，产生恒假矛盾！",
                                conflicting_predicates=col_raw_predicates.get(col, [])
                            )

        # 8. 检查等值与 NOT IN 矛盾: col = '1' AND col NOT IN ('1', '2')
        for col, eq_vals in col_equalities.items():
            if col in col_not_in_lists:
                not_in_vals = col_not_in_lists[col]
                conflict = eq_vals.intersection(not_in_vals)
                if conflict:
                    val = next(iter(conflict))
                    return ContradictionViolation(
                        column=col,
                        message=f"字段 `{col}` 要求等于 '{val}'，但同时出现在 NOT IN 排除列表中，产生恒假矛盾！",
                        conflicting_predicates=col_raw_predicates.get(col, [])
                    )

        # 9. 检查 IN 允许列表被 NOT IN 完全排除: col IN ('1') AND col NOT IN ('1', '2')
        for col, in_vals in col_in_lists.items():
            if col in col_not_in_lists:
                not_in_vals = col_not_in_lists[col]
                if in_vals.issubset(not_in_vals):
                    return ContradictionViolation(
                        column=col,
                        message=f"字段 `{col}` 的 IN 允许列表 {sorted(list(in_vals))} 已被 NOT IN 排除列表完全排除，导致恒假空集！",
                        conflicting_predicates=col_raw_predicates.get(col, [])
                    )

        return None

    @classmethod
    def _flatten_and(cls, node: exp.Expression) -> List[exp.Expression]:
        """将 AND 表达式递归扁平化"""
        if isinstance(node, exp.And):
            return cls._flatten_and(node.left) + cls._flatten_and(node.right)
        return [node]

    @classmethod
    def _classify_predicate(cls, node: exp.Expression) -> Tuple[Optional[str], Optional[str], Any, str]:
        """
        分析单个谓词表达式。
        返回: (column_name, pred_type, normalized_value, raw_repr)
        pred_type ∈ {"EQ", "NEQ", "NOT_LIKE", "LIKE", "GT", "GTE", "LT", "LTE", "IN", "IS_NULL", "IS_NOT_NULL"}
        """
        raw_repr = node.sql()

        # 处理 exp.EQ (col = 'val')
        if isinstance(node, exp.EQ):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "EQ", val, raw_repr)

        # 处理 exp.NEQ (col != 'val' 或 col <> 'val')
        if isinstance(node, exp.NEQ):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "NEQ", val, raw_repr)

        # 处理 exp.GT, exp.GTE, exp.LT, exp.LTE
        if isinstance(node, exp.GT):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "GT", val, raw_repr)

        if isinstance(node, exp.GTE):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "GTE", val, raw_repr)

        if isinstance(node, exp.LT):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "LT", val, raw_repr)

        if isinstance(node, exp.LTE):
            col = cls._extract_col_name(node.left)
            val = cls._extract_literal(node.right)
            if col and val is not None:
                return (col, "LTE", val, raw_repr)

        # 处理 exp.In
        if isinstance(node, exp.In):
            col = cls._extract_col_name(node.this)
            vals = {cls._extract_literal(e) for e in node.expressions if cls._extract_literal(e) is not None}
            if col:
                if "NOT" in raw_repr.upper() or node.args.get("is_not"):
                    return (col, "NOT_IN", vals, raw_repr)
                return (col, "IN", vals, raw_repr)

        # 处理 exp.Is (IS NULL / IS NOT NULL)
        if isinstance(node, exp.Is):
            col = cls._extract_col_name(node.this)
            if col:
                if "NOT" in raw_repr.upper():
                    return (col, "IS_NOT_NULL", None, raw_repr)
                return (col, "IS_NULL", None, raw_repr)

        # 处理 NOT (...)
        if isinstance(node, exp.Not):
            inner = node.this
            if isinstance(inner, (exp.Like, exp.ILike)):
                col = cls._extract_col_name(inner.this)
                val = cls._extract_literal(inner.expression)
                if col and val is not None:
                    return (col, "NOT_LIKE", val, raw_repr)
            elif isinstance(inner, exp.EQ):
                col = cls._extract_col_name(inner.left)
                val = cls._extract_literal(inner.right)
                if col and val is not None:
                    return (col, "NEQ", val, raw_repr)
            elif isinstance(inner, exp.In):
                col = cls._extract_col_name(inner.this)
                vals = {cls._extract_literal(e) for e in inner.expressions if cls._extract_literal(e) is not None}
                if col:
                    return (col, "NOT_IN", vals, raw_repr)
            elif isinstance(inner, exp.Is):
                col = cls._extract_col_name(inner.this)
                if col:
                    return (col, "IS_NOT_NULL", None, raw_repr)

        # 处理直接的 NOT LIKE (在某些 AST 中表示为 exp.Like 且带有否定属性)
        if isinstance(node, (exp.Like, exp.ILike)):
            col = cls._extract_col_name(node.this)
            val = cls._extract_literal(node.expression)
            if "NOT" in raw_repr.upper():
                if col and val is not None:
                    return (col, "NOT_LIKE", val, raw_repr)
            else:
                if col and val is not None:
                    return (col, "LIKE", val, raw_repr)

        return (None, None, None, raw_repr)

    @classmethod
    def _extract_col_name(cls, expr: exp.Expression) -> Optional[str]:
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

    @classmethod
    def _extract_literal(cls, expr: exp.Expression) -> Optional[str]:
        if isinstance(expr, exp.Literal):
            return str(expr.this)
        return None

    @classmethod
    def _parse_comparable_value(cls, val_obj: Any) -> Optional[float]:
        """
        解析可排序比较的值（数值 float 或 ISO 日期/时间戳）。
        """
        if val_obj is None:
            return None
        # 1. 直接 float 转换
        try:
            return float(val_obj)
        except (ValueError, TypeError):
            pass

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
                except Exception:
                    pass
        return None
