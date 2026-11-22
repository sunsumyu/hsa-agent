"""
tests/unit/skills/test_sql_complexity_auditor_red.py
===================================================
测试驱动开发 (TDD) 红灯测试:
验证 SQL 算力代价与 ClickHouse 分区裁剪审计深模块 (sql_complexity_auditor)
"""

import pytest
import sqlglot
from app.skills.security import SQLComplexityError
from app.skills.sql.sql_complexity_auditor import audit_expression_complexity


def test_audit_complexity_small_table_pass():
    # 纯字典表或小表，无需时间过滤直接通过
    ast = sqlglot.parse_one("SELECT * FROM fqz_admdvs", read="clickhouse")
    # 不抛异常即为通过
    audit_expression_complexity(ast)


def test_audit_complexity_large_table_no_filter_fails():
    # 扫描主表 fqz_gz_jzsj_all_ql 无任何过滤，必须拦截防 OOM
    ast = sqlglot.parse_one("SELECT * FROM fqz_gz_jzsj_all_ql", read="clickhouse")
    with pytest.raises(SQLComplexityError) as exc_info:
        audit_expression_complexity(ast)
    assert "必须显式提供 setl_time 或 start_date 时间区间" in str(exc_info.value)


def test_audit_complexity_large_table_with_time_filter_pass():
    # 携带时间区间过滤，允许通过
    ast = sqlglot.parse_one(
        "SELECT * FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'",
        read="clickhouse",
    )
    audit_expression_complexity(ast)


def test_audit_complexity_large_table_with_wrapped_time_filter_pass():
    # 携带函数包裹的时间条件，允许通过
    ast = sqlglot.parse_one(
        "SELECT * FROM fqz_gz_jzsj_all_ql WHERE toYear(toDateTime(setl_time)) = 2024",
        read="clickhouse",
    )
    audit_expression_complexity(ast)


def test_audit_complexity_large_table_with_index_filter_pass():
    # 携带 psn_no 索引过滤（调查模式），允许通过
    ast = sqlglot.parse_one(
        "SELECT * FROM fqz_gz_jzsj_all_ql WHERE psn_no = 'P12345'",
        read="clickhouse",
    )
    audit_expression_complexity(ast)


def test_audit_complexity_heavy_join_without_index_fails():
    # 两张大表关联，无 psn_no 过滤，必须拦截
    ast = sqlglot.parse_one(
        "SELECT a.*, b.* FROM fqz_gz_jzsj_all_ql a JOIN fqz_fymx_test b ON a.id = b.id WHERE a.setl_time >= '2024-01-01'",
        read="clickhouse",
    )
    with pytest.raises(SQLComplexityError) as exc_info:
        audit_expression_complexity(ast)
    assert "检测到大表间关联操作" in str(exc_info.value)
