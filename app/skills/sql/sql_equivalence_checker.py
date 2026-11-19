"""
app/skills/sql_equivalence_checker.py
=====================================
[Matt Pocock Deep Module] AST 级 SQL 语义等价性检查器深模块

核心职责：
通过 AST 语法树遍历、标识符大小写归一化与 sqlglot 优化器，精准判断两个 SQL 是否在语义上等价。
"""

from __future__ import annotations
from typing import Tuple
from sqlglot import exp, parse_one
from sqlglot.optimizer import optimize
from loguru import logger


def check_sql_semantic_equivalence(
    sql1: str,
    sql2: str,
    dialect: str = "clickhouse"
) -> Tuple[bool, str]:
    """深度逻辑对比：通过 AST 树判断两个 SQL 是否在语义上等价"""
    try:
        # 1. 解析并转换标识符大小写为统一小写
        tree1 = parse_one(sql1, read=dialect).transform(
            lambda node: node.copy() if not isinstance(node, exp.Identifier) else exp.Identifier(this=node.this.lower(), quoted=node.args.get("quoted"))
        )
        tree2 = parse_one(sql2, read=dialect).transform(
            lambda node: node.copy() if not isinstance(node, exp.Identifier) else exp.Identifier(this=node.this.lower(), quoted=node.args.get("quoted"))
        )
        
        # 2. 全量语义优化
        tree1 = optimize(tree1)
        tree2 = optimize(tree2)
        
        # 3. 规范化 SQL 字符串严格比对
        norm_sql1 = tree1.sql(dialect=dialect, normalize_functions=True, pad=0, pretty=False)
        norm_sql2 = tree2.sql(dialect=dialect, normalize_functions=True, pad=0, pretty=False)
        
        if norm_sql1 == norm_sql2:
            return True, "语义完全等价 (AST 归一化后匹配)"

        return False, "逻辑不一致 (发现实质性差异)"

    except Exception as e:
        logger.error(f"SQL AST 解析失败: {e}")
        return False, f"解析异常: {str(e)}"
