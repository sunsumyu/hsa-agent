"""
Unit tests for SQLGuardian security checks.

Tests cover the pure-logic methods and early-stage interception (before
schema_registry / field_kg are consulted). Full validate_sql with table
whitelist validation requires live schema_registry and is covered by
integration tests.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.skills.security import SQLGuardian, SecurityViolationError, SQLComplexityError


# ── ensure_limit ──────────────────────────────────────────────

class TestEnsureLimit:
    def test_adds_limit_when_missing(self):
        sql = "SELECT * FROM FQZ_GZ_JZSJ_ALL_QL"
        result = SQLGuardian.ensure_limit(sql, default_limit=100)
        assert "LIMIT 100" in result

    def test_preserves_existing_limit(self):
        sql = "SELECT * FROM FQZ_GZ_JZSJ_ALL_QL LIMIT 50"
        result = SQLGuardian.ensure_limit(sql)
        assert result == sql

    def test_inserts_before_settings(self):
        sql = "SELECT * FROM FQZ_GZ_JZSJ_ALL_QL SETTINGS max_execution_time=30"
        result = SQLGuardian.ensure_limit(sql, default_limit=200)
        assert "LIMIT 200" in result
        # LIMIT should come before SETTINGS
        assert result.index("LIMIT") < result.index("SETTINGS")


# ── check_result_reasonableness ───────────────────────────────

class TestCheckResultReasonableness:
    def test_join_without_on_rejected(self):
        sql = "SELECT * FROM A JOIN B"
        with pytest.raises(SQLComplexityError, match="笛卡尔积"):
            SQLGuardian.check_result_reasonableness(sql, [], [])

    def test_join_with_on_passes(self):
        sql = "SELECT * FROM A JOIN B ON A.id = B.id"
        assert SQLGuardian.check_result_reasonableness(sql, [], []) is True

    def test_join_with_using_passes(self):
        # Note: check_result_reasonableness looks for " USING " with
        # trailing space, so USING(id) without space is a false positive.
        sql = "SELECT * FROM A JOIN B USING (id)"
        assert SQLGuardian.check_result_reasonableness(sql, [], []) is True

    def test_join_using_no_space_false_positive(self):
        """Known edge case: USING(id) without space after USING triggers false positive."""
        sql = "SELECT * FROM A JOIN B USING(id)"
        with pytest.raises(SQLComplexityError):
            SQLGuardian.check_result_reasonableness(sql, [], [])

    def test_no_join_passes(self):
        sql = "SELECT * FROM FQZ_GZ_JZSJ_ALL_QL"
        assert SQLGuardian.check_result_reasonableness(sql, [], []) is True


# ── validate_business_logic ───────────────────────────────────

class TestValidateBusinessLogic:
    def test_empty_rows_passes(self):
        assert SQLGuardian.validate_business_logic([]) is True

    def test_normal_row_passes(self):
        rows = [{"medfee_sumamt": 100.0, "fund_pay_sumamt": 80.0}]
        assert SQLGuardian.validate_business_logic(rows) is True

    def test_fund_exceeds_medfee_rejected(self):
        rows = [{"medfee_sumamt": 100.0, "fund_pay_sumamt": 200.0}]
        assert SQLGuardian.validate_business_logic(rows) is False

    def test_negative_medfee_rejected(self):
        rows = [{"medfee_sumamt": -10.0, "fund_pay_sumamt": 0}]
        assert SQLGuardian.validate_business_logic(rows) is False

    def test_uses_amount_fallback(self):
        rows = [{"amount": 100.0, "fund_pay": 50.0}]
        assert SQLGuardian.validate_business_logic(rows) is True


# ── _suggest_field ────────────────────────────────────────────

class TestSuggestField:
    def test_known_hallucination_fee_amt(self):
        result = SQLGuardian._suggest_field("fee_amt")
        assert "medfee_sumamt" in result

    def test_known_hallucination_hospital_name(self):
        result = SQLGuardian._suggest_field("hospital_name")
        assert "fixmedins_name" in result

    def test_known_hallucination_gender(self):
        result = SQLGuardian._suggest_field("gender")
        assert "gend" in result

    def test_virtual_field_vix(self):
        result = SQLGuardian._suggest_field("vix")
        assert "stddevPop" in result

    def test_unknown_field(self):
        result = SQLGuardian._suggest_field("xyz_nonexistent")
        assert "无法" in result or "不存在" in result


# ── validate_sql: early interception (before schema_registry) ─

class TestValidateSqlEarlyChecks:
    def test_empty_sql_rejected(self):
        with pytest.raises(SecurityViolationError, match="不能为空"):
            SQLGuardian.validate_sql("")

    def test_none_sql_rejected(self):
        with pytest.raises(SecurityViolationError, match="不能为空"):
            SQLGuardian.validate_sql(None)

    def test_mongo_operator_gte_rejected(self):
        with pytest.raises(SecurityViolationError, match="MongoDB"):
            SQLGuardian.validate_sql("SELECT * FROM FQZ_GZ_JZSJ_ALL_QL WHERE {$gte: '2024-01-01'}")

    def test_mongo_operator_in_rejected(self):
        with pytest.raises(SecurityViolationError, match="MongoDB"):
            SQLGuardian.validate_sql("SELECT * FROM FQZ WHERE col $in (1,2,3)")

    def test_stacked_query_rejected(self):
        with pytest.raises(SecurityViolationError, match="堆叠查询"):
            SQLGuardian.validate_sql("SELECT 1; DROP TABLE FQZ_GZ_JZSJ_ALL_QL")

    def test_stacked_query_with_chinese_semicolon_rejected(self):
        with pytest.raises(SecurityViolationError, match="堆叠查询"):
            SQLGuardian.validate_sql("SELECT 1；DROP TABLE FQZ_GZ_JZSJ_ALL_QL")

    def test_semicolon_inside_string_literal_not_flagged(self):
        """Semicolons inside string literals should not trigger stacked query detection."""
        # This should pass the stacked-query check (may fail later on schema validation,
        # but should NOT raise SecurityViolationError for stacking)
        with pytest.raises(SecurityViolationError) as exc_info:
            SQLGuardian.validate_sql(
                "SELECT * FROM FQZ_GZ_JZSJ_ALL_QL WHERE name = 'hello;world'"
            )
        # Should not be a stacking error — it should fail on table/field validation instead
        assert "堆叠查询" not in str(exc_info.value)

    def test_syntax_error_rejected(self):
        with pytest.raises(SecurityViolationError, match="解析失败"):
            SQLGuardian.validate_sql("SELCT FORM TABLE")
