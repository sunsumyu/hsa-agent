"""
Red unit tests for sql_result_sanitizer deep module.
Tests:
- sanitize_sql_results (circuit breaker, garbage cleaning, desensitization)
- inject_tenant_administrative_isolation (district, city, invalid formats, where clauses)
"""

import os
import pytest
from app.skills.sql.sql_result_sanitizer import (
    sanitize_sql_results,
    inject_tenant_administrative_isolation,
)


class TestSqlResultSanitizer:
    def test_sanitize_normal_records(self):
        records = [
            {"psn_name": "张三", "cnt": 50},
            {"psn_name": "李四", "cnt": 120},
        ]
        res = sanitize_sql_results(records, tolerance=500)
        assert len(res) == 2
        assert res[0]["cnt"] == 50

    def test_sanitize_circuit_breaker_melt(self):
        # Count > 200000 triggers melt limit
        bad_records = [{"total_count": 250000}]
        with pytest.raises(ValueError, match="异常明细爆炸"):
            sanitize_sql_results(bad_records)

    def test_sanitize_garbage_encoding(self):
        records = [{"val": "正常数据\ufffd测试"}]
        res = sanitize_sql_results(records)
        assert res[0]["val"] == "[数据源乱码/GBK编码冲突]"

    def test_sanitize_binary_control_chars_default_mode(self, monkeypatch):
        monkeypatch.setenv("IS_BENCHMARK_MODE", "false")
        records = [{"secret": "ABC\x01DEF"}]
        res = sanitize_sql_results(records)
        assert res[0]["secret"] == "[REDACTED/ENCRYPTED]"

    def test_sanitize_binary_control_chars_benchmark_mode(self, monkeypatch):
        monkeypatch.setenv("IS_BENCHMARK_MODE", "true")
        records = [{"secret": "ABC\x01DEF"}]
        res = sanitize_sql_results(records)
        # Len > 4 masks middle chars
        assert res[0]["secret"] == "AB**EF"


class TestAdminIsolationInjection:
    def test_inject_district_tenant(self):
        sql = "SELECT * FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 100"
        injected = inject_tenant_administrative_isolation(sql, "DIST_310115")
        assert "admdvs = '310115'" in injected
        assert "WHERE admdvs = '310115' AND medfee_sumamt > 100" in injected

    def test_inject_city_tenant_without_where(self):
        sql = "SELECT * FROM fqz_gz_jzsj_all_ql GROUP BY setl_id"
        injected = inject_tenant_administrative_isolation(sql, "CITY_310100")
        assert "WHERE admdvs LIKE '3101%'" in injected
        assert "GROUP BY setl_id" in injected

    def test_skip_injection_if_admdvs_already_present(self):
        sql = "SELECT * FROM fqz_gz_jzsj_all_ql WHERE admdvs = '310100'"
        injected = inject_tenant_administrative_isolation(sql, "DIST_310115")
        # Unchanged because admdvs is already checked
        assert injected == sql

    def test_skip_injection_for_invalid_tenant(self):
        sql = "SELECT * FROM fqz_gz_jzsj_all_ql"
        injected = inject_tenant_administrative_isolation(sql, "MALICIOUS_TENANT_FORMAT")
        assert injected == sql
