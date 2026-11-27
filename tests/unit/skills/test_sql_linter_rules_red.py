"""
tests/unit/skills/test_sql_linter_rules_red.py
==============================================
红灯测试：SQL 校验规则链与 AST 语义等价性深度解耦
验证 sql_linter_rules 与 sql_equivalence_checker
"""

import pytest

from app.skills.sql.sql_linter_rules import (
    validate_pk_group_by,
    validate_dynamic_governance,
    validate_join_cartesian,
    run_sql_linter_pipeline,
)
from app.skills.sql.sql_equivalence_checker import check_sql_semantic_equivalence
from app.skills.sql.sql_validator import SQLLogicValidator, sql_validator


def test_validate_pk_group_by_blocks_unique_ids():
    """测试聚合查询按 msg_id 或 rec_id 分组被拦截"""
    sql = "SELECT count(*), msg_id FROM fqz_gz_jzsj_all_ql GROUP BY msg_id"
    ok, err = validate_pk_group_by(sql)
    assert ok is False
    assert "禁止按唯一流水记录 ID" in err


def test_validate_dynamic_governance_temporal_check():
    """测试重复住院场景下禁止使用 setl_time"""
    sql = "SELECT psn_no FROM fqz_gz_jzsj_all_ql WHERE 重复住院 = 1 AND setl_time >= '2024-01-01'"
    ok, err = validate_dynamic_governance(sql)
    assert ok is False
    assert "时间维度准确性校验" in err


def test_validate_join_cartesian_allows_valid_join():
    """测试合法带 ON 条件的 JOIN 放行"""
    sql = "SELECT a.psn_no FROM fqz_fymx_test AS a INNER JOIN fqz_admdvs AS b ON a.admdvs = b.admdvs"
    ok, err = validate_join_cartesian(sql)
    assert ok is True
    assert err == ""


def test_run_sql_linter_pipeline_end_to_end():
    """测试完整治理流水线拦截与放行"""
    # 违规 SQL: 缺失 ON 的 JOIN
    bad_sql = "SELECT * FROM fqz_fymx_test a LEFT JOIN fqz_admdvs b"
    ok, err = run_sql_linter_pipeline(bad_sql)
    assert ok is False
    assert "JOIN 语句缺失关联条件" in err

    # 合法 SQL
    good_sql = "SELECT count(*) FROM fqz_fymx_test WHERE gend LIKE '1%'"
    ok, err = run_sql_linter_pipeline(good_sql)
    assert ok is True
    assert err == ""


def test_check_sql_semantic_equivalence():
    """测试 AST 语义等价性"""
    sql1 = "SELECT PSN_NO, SUM(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = '1' GROUP BY PSN_NO"
    sql2 = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = '1' GROUP BY psn_no"
    eq, msg = check_sql_semantic_equivalence(sql1, sql2)
    assert eq is True
    assert "语义完全等价" in msg

    sql3 = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = '2' GROUP BY psn_no"
    eq, msg = check_sql_semantic_equivalence(sql1, sql3)
    assert eq is False


def test_sql_validator_facade_backward_compatibility():
    """测试 SQLLogicValidator 门面向后兼容"""
    ok, msg = SQLLogicValidator.agentic_linter("SELECT * FROM fqz_fymx_test")
    assert ok is True

    eq, _ = SQLLogicValidator.are_equivalent("SELECT 1", "SELECT 1")
    assert eq is True
