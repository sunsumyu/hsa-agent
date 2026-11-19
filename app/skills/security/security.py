"""
app/skills/security.py
======================
[V71.0 / SPEC-227 / Matt Pocock Deep Module] 生产级 SQL 安全哨兵门面 (SQLGuardian)

作为统一门面串联：
1. 语法预检与防注入: SQLInjectionGuard
2. 架构接缝与字段知识图谱纠错: SchemaGrounder, FieldKnowledgeGraph
3. 静态 AST 深度安全审计: SQLASTSecurityAuditor
4. ClickHouse 方言陷阱自愈: ClickHouseDialectHealer
5. 字段物理真理对撞: validate_column_and_function_existence
6. 代价与分区裁剪审计: audit_expression_complexity
"""

from __future__ import annotations
import re
from typing import List, Optional
from sqlglot import exp
from loguru import logger

from app.core.registry.schema_registry import schema_registry


class SecurityViolationError(Exception):
    """物理安全或算力限制违规异常"""
    pass


class SQLComplexityError(SecurityViolationError):
    """查询代价过高导致的拦截异常"""
    pass


class SQLGuardian:
    """生产级 SQL 安全哨兵门面：执行语义级别的物理拦截。"""

    FORBIDDEN_KEYWORDS = [
        "DROP", "TRUNCATE", "DELETE", "UPDATE", "ALTER",
        "GRANT", "REVOKE", "REPLACE", "INSERT", "CREATE",
        "RENAME", "SYSTEM", "KILL"
    ]

    @classmethod
    def validate_sql(
        cls,
        sql: str,
        tenant_id: Optional[str] = None,
        expected_table: Optional[str] = None,
    ) -> str:
        """
        [V173.0] 物理校验并执行行政区划隔离 + 场景-表映射强制验证。

        Args:
            sql: 待校验的 SQL
            tenant_id: 租户 ID（用于行政区划隔离）
            expected_table: 预期的目标表名（由 SceneTableSelector 提供）
        """
        from app.skills.sql_injection_guard import SQLInjectionGuard
        from app.skills.sql_ast_security_auditor import SQLASTSecurityAuditor

        # 1. 语法预检、字面量规整与防注入校验 (NoSQL & 堆叠分号拦截)
        clean_sql = SQLInjectionGuard.clean_and_check_injection(sql)

        # 2. 确定性架构接缝修复 (Deterministic Schema Seam via SchemaGrounder)
        from app.core.tool_engine.grounder import SchemaGrounder
        clean_sql, _, _ = SchemaGrounder.ground_sql(clean_sql)

        # 3. 字段知识图谱纠错
        try:
            from app.infra.neo4j_manager import field_kg
            clean_sql, kg_warnings = field_kg.sanitize_sql(clean_sql)
            if kg_warnings:
                logger.warning(
                    f"[SQLGuardian+FieldKG] 字段自动纠错 ({len(kg_warnings)} 处): {'; '.join(kg_warnings)}"
                )
        except Exception as kg_err:
            logger.debug(f"[SQLGuardian] FieldKG 不可用，跳过字段纠错: {kg_err}")

        # 4. AST 语法树解析与恒假语义拦截
        expression = SQLASTSecurityAuditor.parse_ast(clean_sql)
        SQLASTSecurityAuditor.audit_contradiction(clean_sql)

        # 5. 表名白名单与场景表映射校验
        SQLASTSecurityAuditor.audit_table_whitelist(expression)
        SQLASTSecurityAuditor.audit_expected_table(expression, expected_table=expected_table)

        # 6. 非法操作指令与深层 DDL/DML 节点拦截
        SQLASTSecurityAuditor.audit_disallowed_nodes(expression)

        # 7. 方言物理陷阱自动修复 (ClickHouseDialectHealer)
        expression = cls._refine_sql_traps(expression)

        # 8. 严格字段与函数物理真理对撞
        cls._validate_column_existence(expression)

        # 9. 代价与算力审计
        cls._audit_expression_complexity(expression)

        # 10. ClickHouse 物理表名大小写自动对齐
        SQLASTSecurityAuditor.align_table_case(expression)

        # 11. 行政区划统筹区逻辑隔离注入
        expression = SQLASTSecurityAuditor.inject_tenant_isolation(expression, tenant_id=tenant_id)

        return expression.sql(dialect="clickhouse")

    @staticmethod
    def _extract_tables_from_ast(expression: exp.Expression) -> List[str]:
        """向后兼容委托至 SQLASTSecurityAuditor"""
        from app.skills.sql_ast_security_auditor import SQLASTSecurityAuditor
        return SQLASTSecurityAuditor.extract_tables(expression)

    @staticmethod
    def _inject_tenant_isolation(expression: exp.Expression, tenant_id: str) -> exp.Expression:
        """向后兼容委托至 SQLASTSecurityAuditor"""
        from app.skills.sql_ast_security_auditor import SQLASTSecurityAuditor
        return SQLASTSecurityAuditor.inject_tenant_isolation(expression, tenant_id)

    @staticmethod
    def _validate_column_existence(expression: exp.Expression) -> None:
        """[Matt Pocock Deep Module] 委托至专职的字段与函数物理真理对撞深模块"""
        from app.skills.schema_truth_validator import validate_column_and_function_existence
        validate_column_and_function_existence(expression)

    @staticmethod
    def _suggest_field(hallucinated: str) -> str:
        """[Matt Pocock Deep Module] 委托至专职的幻觉字段纠错建议深模块"""
        from app.skills.schema_truth_validator import suggest_field_replacement
        return suggest_field_replacement(hallucinated)

    @staticmethod
    def _refine_sql_traps(expression: exp.Expression) -> exp.Expression:
        """[V228.0 Matt Pocock Deep Module] 委托至 ClickHouseDialectHealer 深模块执行 AST 级方言自愈"""
        from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer
        return ClickHouseDialectHealer.heal_expression(expression)

    @staticmethod
    def _audit_expression_complexity(expression: exp.Expression) -> None:
        """[Matt Pocock Deep Module] 委托至专职的算力代价与分区裁剪审计深模块"""
        from app.skills.sql_complexity_auditor import audit_expression_complexity
        audit_expression_complexity(expression)

    @staticmethod
    def inject_settings(sql: str) -> str:
        sql = sql.strip().rstrip(";")
        max_time = schema_registry.get_max_execution_time()
        max_mem = schema_registry.get_max_memory_usage()
        quota_settings = (
            f"SETTINGS max_execution_time={max_time}, "
            f"max_memory_usage={max_mem}, readonly=1"
        )
        if "SETTINGS" not in sql.upper():
            return f"{sql}\n{quota_settings}"
        return sql

    @staticmethod
    def ensure_limit(sql: str, default_limit: int = 500) -> str:
        if "LIMIT" in sql.upper():
            return sql
        settings_match = re.search(r'\bSETTINGS\b', sql, re.IGNORECASE)
        if settings_match:
            idx = settings_match.start()
            return f"{sql[:idx].rstrip()} LIMIT {default_limit} {sql[idx:]}"
        return f"{sql.strip().rstrip(';')} LIMIT {default_limit}"

    @staticmethod
    def check_result_reasonableness(sql: str, results: list, tasks: list) -> bool:
        sql_u = sql.upper()
        if "JOIN" in sql_u and not any(k in sql_u for k in [" ON ", " USING ", " CROSS "]):
            raise SQLComplexityError("🚨 物理防御拦截：SQL 包含 JOIN 但未发现关联条件，疑似存在笛卡尔积风险。")
        return True

    @staticmethod
    def validate_business_logic(rows: list) -> bool:
        if not rows:
            return True
        for row in rows:
            if isinstance(row, dict):
                medfee = float(row.get("medfee_sumamt", row.get("amount", 0)) or 0)
                fund = float(row.get("fund_pay_sumamt", row.get("fund_pay", 0)) or 0)
                if medfee > 0 and fund > medfee * 1.01:
                    return False
                if medfee < -0.01:
                    return False
        return True
