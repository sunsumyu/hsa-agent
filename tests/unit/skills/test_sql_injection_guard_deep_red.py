import pytest
from app.skills.security import SecurityViolationError
from app.skills.sql.sql_injection_guard import SQLInjectionGuard
from app.skills.sql.sql_ast_security_auditor import SQLASTSecurityAuditor


class TestSQLInjectionGuard:
    def test_empty_sql_raises(self):
        with pytest.raises(SecurityViolationError, match="不能为空"):
            SQLInjectionGuard.clean_and_check_injection("")
        with pytest.raises(SecurityViolationError, match="不能为空"):
            SQLInjectionGuard.clean_and_check_injection(None)

    def test_mongo_operator_interception(self):
        with pytest.raises(SecurityViolationError, match="MongoDB"):
            SQLInjectionGuard.clean_and_check_injection("SELECT * FROM t WHERE {$gt: 100}")

    def test_stacked_query_interception(self):
        with pytest.raises(SecurityViolationError, match="堆叠查询"):
            SQLInjectionGuard.clean_and_check_injection("SELECT 1; DROP TABLE users")
        with pytest.raises(SecurityViolationError, match="堆叠查询"):
            SQLInjectionGuard.clean_and_check_injection("SELECT 1；DROP TABLE users")

    def test_semicolon_in_literal_allowed(self):
        sql = "SELECT * FROM t WHERE comment = 'a;b;c'"
        cleaned = SQLInjectionGuard.clean_and_check_injection(sql)
        assert cleaned == sql


class TestSQLASTSecurityAuditor:
    def test_syntax_error(self):
        with pytest.raises(SecurityViolationError, match="解析失败"):
            SQLASTSecurityAuditor.parse_ast("SELECT FROM TABLE WHERE")

    def test_table_whitelist_and_hallucination(self):
        expr = SQLASTSecurityAuditor.parse_ast("SELECT * FROM completely_fake_table")
        with pytest.raises(SecurityViolationError, match="虚假幻觉表"):
            SQLASTSecurityAuditor.audit_table_whitelist(expr)

    def test_expected_table_mismatch(self):
        expr = SQLASTSecurityAuditor.parse_ast("SELECT * FROM fqz_fymx_test")
        with pytest.raises(SecurityViolationError, match="场景-表映射违规"):
            SQLASTSecurityAuditor.audit_expected_table(expr, expected_table="fqz_gz_jzsj_all_ql")

    def test_disallowed_ddl_nodes(self):
        expr = SQLASTSecurityAuditor.parse_ast("SELECT 1")
        # 正常 SELECT 不报错
        SQLASTSecurityAuditor.audit_disallowed_nodes(expr)

    def test_tenant_isolation_injection(self):
        expr = SQLASTSecurityAuditor.parse_ast("SELECT * FROM fqz_fymx_test WHERE medfee_sumamt > 100")
        injected = SQLASTSecurityAuditor.inject_tenant_isolation(expr, tenant_id="440100")
        sql = injected.sql(dialect="clickhouse")
        assert "aaa027 = '440100'" in sql
