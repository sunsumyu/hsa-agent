"""
[SPEC-227 / Matt Pocock Deep Module] SQL AST 语法树安全与白名单审计深模块 (SQLASTSecurityAuditor)

专职负责基于 sqlglot AST 的语法解析、恒假矛盾条件探测、表名白名单校验、
场景-表映射强制对撞、DDL/DML 非法节点审计、表名大小写自动纠偏及租户统筹区隔离注入。
"""

from __future__ import annotations
from typing import List, Optional, Set
import sqlglot
from sqlglot import exp
from loguru import logger

from app.skills.security import SecurityViolationError
from app.core.registry.schema_registry import schema_registry


class SQLASTSecurityAuditor:
    """SQL AST 语法树深度安全审计器"""

    ALLOWED_KEYS = ("select", "with", "show", "describe", "explain", "union")
    FORBIDDEN_NODES = (exp.Drop, exp.Update, exp.Delete, exp.Alter, exp.Create, exp.Insert)

    @classmethod
    def parse_ast(cls, clean_sql: str) -> exp.Expression:
        """解析为 ClickHouse 方言 AST 语法树"""
        try:
            return sqlglot.parse_one(clean_sql, read="clickhouse")
        except Exception as pe:
            logger.error(f"[SECURITY] SQL 框架解析失败: {pe}")
            raise SecurityViolationError(f"物理语法解析失败：{str(pe)}。请检查 SQL 结构是否完整。")

    @classmethod
    def audit_contradiction(cls, clean_sql: str) -> None:
        """静态 AST 恒假互斥语义拦截"""
        from app.core.guardrails.contradiction_detector import ContradictionDetector
        contra_violation = ContradictionDetector.detect(clean_sql)
        if contra_violation:
            logger.error(f"[SECURITY] 发现逻辑恒假矛盾条件: {contra_violation.message}")
            raise SecurityViolationError(f"物理拦截：{contra_violation.message}")

    @classmethod
    def audit_table_whitelist(cls, expression: exp.Expression) -> None:
        """表名白名单校验 (从 SchemaRegistry 读取)"""
        from app.core.tool_engine.grounder import SchemaGrounder

        forbidden_tables = {t.lower() for t in schema_registry.get_forbidden_table_names()}
        valid_prefixes = tuple(p.lower() for p in schema_registry.get_valid_prefixes())

        # 收集所有的 CTE 别名，避免误判为物理幻觉表
        cte_names: Set[str] = set()
        for cte in expression.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            is_system_db = bool(table.db and table.db.lower() in {"system", "information_schema"})
            if is_system_db or table_name in cte_names or table_name in {"dual"}:
                continue
            if table_name in forbidden_tables or not any(table_name.startswith(p) for p in valid_prefixes):
                logger.error(f"[SECURITY] 发现物理不存在的幻觉表: {table_name}")
                raise SecurityViolationError(
                    f"物理拦截：表 `{table_name}` 是虚假幻觉表！{SchemaGrounder.get_registered_tables_hint()}。"
                )

    @classmethod
    def audit_expected_table(cls, expression: exp.Expression, expected_table: Optional[str] = None) -> None:
        """场景-表映射强制对撞验证"""
        if not expected_table:
            return

        used_tables = cls.extract_tables(expression)
        expected_lower = expected_table.lower()
        if expected_lower not in used_tables and len(used_tables) > 0:
            wrong_tables = [t for t in used_tables if t != expected_lower]
            logger.error(f"[SECURITY] 场景-表映射违规! 预期: {expected_table}, 实际: {wrong_tables}")
            raise SecurityViolationError(
                f"【表选择强制拦截】检测到场景-表映射违规！\n"
                f"预期表: `{expected_table}`\n"
                f"实际使用的表: `{wrong_tables}`\n"
                f"根据场景关键词分析，当前查询**必须使用 `{expected_table}`**。\n"
                f"请修改 SQL 中的 FROM/JOIN 子句，将 `{wrong_tables[0]}` 替换为 `{expected_table}`。"
            )

    @classmethod
    def audit_disallowed_nodes(cls, expression: exp.Expression) -> None:
        """结构化指令审计 (拦截非查询与 DDL/DML 节点)"""
        if expression.key not in cls.ALLOWED_KEYS:
            logger.warning(f"[SECURITY] 拦截到非查询意图节点 key: {expression.key}")
            raise SecurityViolationError(f"物理拦截：检测到非法 DDL/DML 意图 [{expression.key}]。")

        for node in expression.walk():
            if isinstance(node, cls.FORBIDDEN_NODES):
                logger.error(f"[SECURITY] 在 AST 深层探测到非法节点: {type(node)}")
                raise SecurityViolationError(f"物理拦截：在 SQL 内部发现非法操作节点 {type(node).__name__}。")

    @classmethod
    def align_table_case(cls, expression: exp.Expression) -> None:
        """企业级自愈：自动对齐 ClickHouse 的大小写敏感物理表名"""
        all_physical_tables = {t.lower(): t for t in schema_registry.get_all_table_names()}
        for table_node in expression.find_all(exp.Table):
            t_name = table_node.name
            if not t_name:
                continue
            t_name_lower = t_name.lower()
            if t_name_lower in all_physical_tables:
                actual_name = all_physical_tables[t_name_lower]
                if table_node.this.this != actual_name:
                    logger.warning(
                        f"🔧 [SQLGuardian] 检测到表名大小写差异，已自动修正: {table_node.this.this} -> {actual_name}"
                    )
                    table_node.this.set("this", actual_name)

    @classmethod
    def inject_tenant_isolation(cls, expression: exp.Expression, tenant_id: Optional[str] = None) -> exp.Expression:
        """行政区划隔离注入：通过 AST 改写，强制在 WHERE 子句中追加统筹区分区过滤"""
        if not tenant_id:
            return expression

        where_clause = expression.find(exp.Where)
        where_str = str(where_clause).upper() if where_clause else ""

        if "AAA027" in where_str or "ADMIN_DIVISION" in where_str:
            return expression

        if isinstance(expression, exp.Select):
            return expression.where(f"aaa027 = '{tenant_id}'", append=True)

        return expression

    @classmethod
    def extract_tables(cls, expression: exp.Expression) -> List[str]:
        """从 AST 中提取所有 fqz_ 开头的物理表名"""
        tables = []
        for table_node in expression.find_all(exp.Table):
            table_name = table_node.name.lower()
            if table_name.startswith("fqz_"):
                tables.append(table_name)
        return tables
