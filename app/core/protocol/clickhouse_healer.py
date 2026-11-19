"""
app/core/protocol/clickhouse_healer.py
======================================
[Matt Pocock Deep Module 实践]
专属于 ClickHouse 的 AST 级物理语法与方言自愈引擎。

- Interface: 极简，暴露 heal(sql: str) -> str 与 heal_expression(expr) -> Expression
- Implementation: 内部消化所有 ClickHouse 语法与方言特异性：
  1. MySQL 常用方言函数平滑重写 (DATEDIFF, IFNULL, YEAR, MONTH, DATE_FORMAT, CURDATE, GROUP_CONCAT)
  2. 日期字段 4 位年份字面量自动转 toYear(toDateTime(...))
  3. 聚合别名遮蔽物理列问题 (ClickHouse Code: 184)
  4. 裸中文标识符引号包裹
  5. 单引号不成对容错修复
- Locality: 将 SQL AST 方言治理彻底与业务执行与安全审计解耦，各司其职
"""

from __future__ import annotations
import re
from typing import Optional
import sqlglot
from sqlglot import exp
from loguru import logger


class ClickHouseDialectHealer:
    """ClickHouse 语法自愈深模块 (Deep Module)"""

    _DATE_FIELDS = frozenset([
        "setl_time", "start_date", "end_date", "fee_ocur_time", "setl_date"
    ])

    @classmethod
    def heal(cls, sql: str) -> str:
        """
        公共契约接口：修复 SQL 文本中的方言、引号、别名遮蔽与非 ASCII 标识符。
        """
        if not sql:
            return ""

        cand = sql.strip()
        cand = cls._strip_markdown_and_enclosures(cand)

        # 尝试通过 AST 进行方言重写与别名修复
        try:
            parsed = sqlglot.parse_one(cand, read="clickhouse")
            if parsed:
                parsed = cls.heal_expression(parsed)
                cand = parsed.sql(dialect="clickhouse")
            cand = cls._fix_shadowing_aliases(cand)
            cand = cls._quote_non_ascii_identifiers(cand)
            return cand
        except Exception:
            pass

        # 容错修复单引号不成对后再次重试
        cand = cls._repair_unpaired_quotes(cand)
        try:
            parsed = sqlglot.parse_one(cand, read="clickhouse")
            if parsed:
                parsed = cls.heal_expression(parsed)
                cand = parsed.sql(dialect="clickhouse")
            cand = cls._fix_shadowing_aliases(cand)
            cand = cls._quote_non_ascii_identifiers(cand)
        except Exception:
            pass

        return cand

    @classmethod
    def heal_expression(cls, expression: exp.Expression) -> exp.Expression:
        """
        AST 级别自愈：直接对已解析的 sqlglot Expression 进行 ClickHouse 方言转换。
        """
        if expression is None:
            return expression

        # 1. 修复日期字段 = 'YYYY' 陷阱 -> toYear(toDateTime(col)) = YYYY
        for eq in expression.find_all(exp.EQ):
            left, right = eq.left, eq.right
            if isinstance(left, exp.Column) and left.name.lower() in cls._DATE_FIELDS:
                if isinstance(right, exp.Literal) and right.is_string and re.match(r"^\d{4}$", str(right.this)):
                    try:
                        new_eq = sqlglot.parse_one(
                            f"toYear(toDateTime({left.sql()})) = {right.this}",
                            read="clickhouse",
                        )
                        eq.replace(new_eq)
                    except Exception:
                        pass

        # 2. 遍历 AST 进行方言函数节点平滑重写
        for node in expression.walk():
            if isinstance(node, (exp.Func, exp.Anonymous)):
                func_name = (
                    getattr(node, "name", "")
                    or getattr(node, "key", "")
                    or node.__class__.__name__
                ).upper()

                # 2.1 MySQL DATEDIFF -> ClickHouse dateDiff('day', B, A)
                if func_name in ("DATEDIFF", "DATE_DIFF"):
                    args = (
                        list(node.expressions)
                        if hasattr(node, "expressions") and node.expressions
                        else [getattr(node, "this", None), getattr(node, "expression", None)]
                    )
                    args = [a for a in args if a is not None]
                    if len(args) == 2:
                        arg1, arg2 = args[0], args[1]
                        new_node = exp.Anonymous(
                            this="dateDiff",
                            expressions=[exp.Literal.string("day"), arg2.copy(), arg1.copy()]
                        )
                        node.replace(new_node)
                        logger.debug(f"[AST自愈] 重写 DATEDIFF 为 dateDiff: {new_node.sql(dialect='clickhouse')}")

                # 2.2 MySQL IFNULL -> ClickHouse ifNull(A, B)
                elif func_name in ("IFNULL", "COALESCE"):
                    args = [getattr(node, "this", None)] if hasattr(node, "this") and node.this is not None else []
                    if hasattr(node, "expressions") and node.expressions:
                        args.extend([e for e in node.expressions if e is not None])
                    elif hasattr(node, "expression") and node.expression is not None:
                        args.append(node.expression)
                    if len(args) == 2:
                        arg1, arg2 = args[0], args[1]
                        new_node = exp.Anonymous(
                            this="ifNull",
                            expressions=[arg1.copy(), arg2.copy()]
                        )
                        node.replace(new_node)
                        logger.debug("[AST自愈] 重写 IFNULL 为 ifNull")

                # 2.3 MySQL YEAR -> ClickHouse toYear(A)
                elif func_name == "YEAR":
                    arg_node = getattr(node, "this", None) or (
                        node.expressions[0] if hasattr(node, "expressions") and node.expressions else None
                    )
                    if arg_node:
                        new_node = sqlglot.parse_one(
                            f"toYear({arg_node.sql(dialect='clickhouse')})", read="clickhouse"
                        )
                        node.replace(new_node)
                        logger.debug("[AST自愈] 重写 YEAR 为 toYear")

                # 2.4 MySQL MONTH -> ClickHouse toMonth(A)
                elif func_name == "MONTH":
                    arg_node = getattr(node, "this", None) or (
                        node.expressions[0] if hasattr(node, "expressions") and node.expressions else None
                    )
                    if arg_node:
                        new_node = sqlglot.parse_one(
                            f"toMonth({arg_node.sql(dialect='clickhouse')})", read="clickhouse"
                        )
                        node.replace(new_node)
                        logger.debug("[AST自愈] 重写 MONTH 为 toMonth")

                # 2.5 MySQL CURDATE -> ClickHouse today()
                elif func_name in ("CURDATE", "CURRENTDATE", "CURRENT_DATE"):
                    new_node = sqlglot.parse_one("today()", read="clickhouse")
                    node.replace(new_node)
                    logger.debug("[AST自愈] 重写 CURDATE 为 today()")

                # 2.6 MySQL GROUP_CONCAT -> ClickHouse arrayStringConcat(groupUniqArray(col), sep)
                elif func_name in ("GROUP_CONCAT", "GROUPCONCAT"):
                    col_node = getattr(node, "this", None) or (
                        node.expressions[0] if hasattr(node, "expressions") and node.expressions else None
                    )
                    sep_node = node.args.get("separator") if hasattr(node, "args") else None
                    if not sep_node and hasattr(node, "expressions") and len(node.expressions) > 1:
                        sep_node = node.expressions[1]
                    sep = sep_node.sql(dialect="clickhouse") if sep_node else "',' "
                    if col_node:
                        col = col_node.sql(dialect="clickhouse")
                        new_node = sqlglot.parse_one(
                            f"arrayStringConcat(groupUniqArray({col}), {sep})", read="clickhouse"
                        )
                        node.replace(new_node)
                        logger.debug("[AST自愈] 重写 GROUP_CONCAT 为 arrayStringConcat")

                # 2.7 MySQL DATE_FORMAT -> ClickHouse formatDateTime
                elif func_name in ("DATE_FORMAT", "DATEFORMAT"):
                    args = (
                        list(node.expressions)
                        if hasattr(node, "expressions") and node.expressions
                        else [getattr(node, "this", None), getattr(node, "expression", None)]
                    )
                    args = [a for a in args if a is not None]
                    if len(args) == 2:
                        arg1, arg2 = args[0].sql(dialect="clickhouse"), args[1].sql(dialect="clickhouse")
                        new_node = sqlglot.parse_one(f"formatDateTime({arg1}, {arg2})", read="clickhouse")
                        node.replace(new_node)
                        logger.debug("[AST自愈] 重写 DATE_FORMAT 为 formatDateTime")

        return expression

    # ──────────────────────────────────────────────────────────────
    # 内部私有实现 (Private Implementation)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _strip_markdown_and_enclosures(cls, sql: str) -> str:
        cand = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE).strip()
        cand = re.sub(r"\s*```+$", "", cand).strip()
        cand = cand.rstrip(";； \n\r\t")
        cand = re.split(r"</[^>]+>", cand)[0].strip()
        cand = re.sub(r'["\}\]\s]+$', "", cand).strip().rstrip(";； \n\r\t")
        return cand

    @classmethod
    def _repair_unpaired_quotes(cls, cand: str) -> str:
        if cand.count("'") % 2 == 1:
            if cand.endswith("'"):
                return cand[:-1].strip()
            return cand + "'"
        return cand

    @classmethod
    def _quote_non_ascii_identifiers(cls, sql: str) -> str:
        try:
            parsed = sqlglot.parse_one(sql, read="clickhouse")
            if not parsed:
                return sql
            modified = False
            for alias_node in parsed.find_all(exp.Alias):
                raw_alias = alias_node.alias or ""
                needs_quote = any(ord(c) > 127 for c in raw_alias) or not raw_alias.isidentifier()
                current_ident = alias_node.args.get("alias")
                is_already_quoted = getattr(current_ident, "quoted", False)
                if needs_quote and not is_already_quoted:
                    alias_node.set("alias", exp.to_identifier(raw_alias, quoted=True))
                    modified = True
            return parsed.sql(dialect="clickhouse") if modified else sql
        except Exception:
            return sql

    @classmethod
    def _fix_shadowing_aliases(cls, sql: str) -> str:
        """修复 ClickHouse 聚合别名遮蔽物理列问题 (Code: 184)"""
        try:
            parsed = sqlglot.parse_one(sql, read="clickhouse")
            if not parsed:
                return sql

            modified = False
            for select_node in parsed.find_all(exp.Select):
                where_node = select_node.args.get("where")
                prewhere_node = select_node.args.get("prewhere")
                if not where_node and not prewhere_node:
                    continue

                from_node = select_node.args.get("from_") or select_node.args.get("from")
                table_target = None
                if from_node:
                    tbl = from_node.find(exp.Table)
                    if tbl:
                        table_target = tbl.alias or tbl.name

                filter_cols = set()
                for fn in (where_node, prewhere_node):
                    if fn:
                        for col in fn.find_all(exp.Column):
                            filter_cols.add(col.name.lower())

                shadow_cols_to_qualify = set()
                for expr in select_node.selects:
                    if isinstance(expr, exp.Alias):
                        raw_alias = expr.alias
                        alias_name = raw_alias.lower()
                        has_agg = bool(list(expr.find_all(exp.AggFunc)))
                        is_literal = isinstance(expr.this, exp.Literal)
                        is_not_plain_col = not (
                            isinstance(expr.this, exp.Column) and expr.this.name.lower() == alias_name
                        )

                        target_alias = raw_alias
                        if filter_cols and has_agg and (alias_name in filter_cols):
                            agg_node = next(expr.find_all(exp.AggFunc))
                            func_name = agg_node.key.lower() if hasattr(agg_node, "key") else "agg"
                            target_alias = f"{func_name}_{raw_alias}"
                            expr.set("alias", exp.to_identifier(target_alias))
                            modified = True
                        elif filter_cols and (alias_name in filter_cols) and (is_literal or is_not_plain_col):
                            if table_target:
                                shadow_cols_to_qualify.add(alias_name)
                            else:
                                target_alias = f"target_{raw_alias}"
                                expr.set("alias", exp.to_identifier(target_alias))
                                modified = True

                if shadow_cols_to_qualify and table_target:
                    for fn in (where_node, prewhere_node):
                        if fn:
                            for col in fn.find_all(exp.Column):
                                if col.name.lower() in shadow_cols_to_qualify and not col.table:
                                    col.set("table", exp.to_identifier(table_target))
                                    modified = True

            return parsed.sql(dialect="clickhouse") if modified else sql
        except Exception:
            return sql
