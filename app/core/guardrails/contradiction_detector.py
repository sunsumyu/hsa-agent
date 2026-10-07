import re
from typing import NamedTuple, List, Optional, Dict, Set, Tuple
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
        col_raw_predicates: Dict[str, List[str]] = {}

        for node in and_conjuncts:
            col_name, pred_type, val_str, raw_repr = cls._classify_predicate(node)
            if not col_name:
                continue

            col_name_lower = col_name.lower()
            col_raw_predicates.setdefault(col_name_lower, []).append(raw_repr)

            if pred_type == "EQ":
                col_equalities.setdefault(col_name_lower, set()).add(val_str)
            elif pred_type == "NEQ":
                col_inequalities.setdefault(col_name_lower, set()).add(val_str)
            elif pred_type == "NOT_LIKE":
                # 提取前缀或基值，例如 '1%' -> '1'
                base_val = val_str.rstrip("%")
                col_not_likes.setdefault(col_name_lower, set()).add(base_val)

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

        # 3. 检查二元枚举字段全排斥: gend NOT LIKE '1%' AND gend NOT LIKE '2%' (或 != '1' AND != '2')
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

        return None

    @classmethod
    def _flatten_and(cls, node: exp.Expression) -> List[exp.Expression]:
        """将 AND 表达式递归扁平化"""
        if isinstance(node, exp.And):
            return cls._flatten_and(node.left) + cls._flatten_and(node.right)
        return [node]

    @classmethod
    def _classify_predicate(cls, node: exp.Expression) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
        """
        分析单个谓词表达式。
        返回: (column_name, pred_type, normalized_value, raw_repr)
        pred_type ∈ {"EQ", "NEQ", "NOT_LIKE", "LIKE"}
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

        # 处理 NOT (col LIKE 'val' 或 col = 'val')
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

        # 处理直接的 NOT LIKE (在某些 AST 中表示为 exp.Like 且带有否定属性)
        if isinstance(node, (exp.Like, exp.ILike)):
            # 检查是否有否定修饰
            col = cls._extract_col_name(node.this)
            val = cls._extract_literal(node.expression)
            # 通过 raw SQL 判定是否包含 NOT
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
