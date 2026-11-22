"""
tests/unit/skills/test_schema_truth_validator_red.py
===================================================
测试驱动开发 (TDD) 红灯测试:
验证 SQL 字段与函数物理真理对撞深模块 (schema_truth_validator)
"""

import pytest
import sqlglot
from app.skills.security import SecurityViolationError
from app.skills.schema.schema_truth_validator import (
    validate_column_and_function_existence,
    suggest_field_replacement,
)


def test_suggest_field_replacement():
    assert "medfee_sumamt" in suggest_field_replacement("fee_amt")
    assert "fixmedins_name" in suggest_field_replacement("hospital_name")
    assert "gend" in suggest_field_replacement("gender")
    assert "非物理字段" in suggest_field_replacement("vix")
    assert "无法自动推测正确字段" in suggest_field_replacement("random_hallucinated_xyz")


def test_validate_column_valid_fields_pass():
    # 真实存在的字段在 fqz_gz_jzsj_all_ql 中通过
    ast = sqlglot.parse_one("SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql", read="clickhouse")
    validate_column_and_function_existence(ast)


def test_validate_column_hallucinated_field_intercept():
    # 彻底未知的幻觉字段必须被拦截并抛出 SecurityViolationError
    ast = sqlglot.parse_one("SELECT xyz_hallucination FROM fqz_gz_jzsj_all_ql", read="clickhouse")
    with pytest.raises(SecurityViolationError) as exc_info:
        validate_column_and_function_existence(ast)
    err = str(exc_info.value)
    assert "字段 `xyz_hallucination` 在当前表" in err


def test_validate_function_unsupported_intercept():
    # 不支持的 year() 函数被拦截
    ast = sqlglot.parse_one("SELECT year(setl_time) FROM fqz_gz_jzsj_all_ql", read="clickhouse")
    with pytest.raises(SecurityViolationError) as exc_info:
        validate_column_and_function_existence(ast)
    assert "检测到非法函数 `year()`" in str(exc_info.value)


def test_validate_column_cte_and_system_exempt():
    # CTE 别名与系统库查询豁免
    ast = sqlglot.parse_one(
        "WITH cte_sub AS (SELECT psn_no FROM fqz_gz_jzsj_all_ql) SELECT psn_no FROM cte_sub",
        read="clickhouse",
    )
    validate_column_and_function_existence(ast)
