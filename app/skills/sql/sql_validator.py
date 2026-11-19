"""
app/skills/sql_validator.py
===========================
[V150.0 / Matt Pocock Deep Module] AST 级 SQL 逻辑等价性与治理校验门面

向后兼容接口：
- SQLLogicValidator.are_equivalent -> sql_equivalence_checker.check_sql_semantic_equivalence
- SQLLogicValidator.agentic_linter -> sql_linter_rules.run_sql_linter_pipeline
- sql_validator (LazyProxy 单例)
"""

from __future__ import annotations
from typing import Tuple

from app.skills.sql_equivalence_checker import check_sql_semantic_equivalence
from app.skills.sql_linter_rules import (
    run_sql_linter_pipeline,
    load_governance_config,
)
from app.core.container import LazyProxy


class SQLLogicValidator:
    """[V150.0] AST 级 SQL 逻辑等价性与治理校验门面"""
    
    @staticmethod
    def are_equivalent(sql1: str, sql2: str, dialect: str = "clickhouse") -> Tuple[bool, str]:
        """[V54.1] 深度逻辑对比：通过 AST 树判断两个 SQL 是否在语义上等价"""
        return check_sql_semantic_equivalence(sql1, sql2, dialect=dialect)

    @staticmethod
    def _load_governance_config():
        """向后兼容配置读取"""
        return load_governance_config()

    @staticmethod
    def agentic_linter(sql: str) -> Tuple[bool, str]:
        """[V150.0] 框架级 SQL 治理引擎：由外部配置驱动，支持跨项目复用"""
        return run_sql_linter_pipeline(sql)


# Backward-compatible alias, delegates to DI container
sql_validator = LazyProxy("sql_validator")
