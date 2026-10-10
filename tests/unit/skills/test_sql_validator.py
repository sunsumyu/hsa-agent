import pytest
from app.skills.sql_validator import SQLLogicValidator

def test_linter_allows_cross_join_with_where_condition():
    sql = """
    WITH max_amt AS (SELECT max(det_item_fee_sumamt) AS max_fee FROM fqz_fymx_test WHERE NOT (det_item_fee_sumamt IS NULL))
    SELECT f.det_item_fee_sumamt, f.hilist_name
    FROM fqz_fymx_test AS f
    CROSS JOIN max_amt AS m
    WHERE f.det_item_fee_sumamt = m.max_fee
    """
    ok, msg = SQLLogicValidator.agentic_linter(sql)
    assert ok is True
    assert msg == ""

def test_linter_blocks_cross_join_without_where():
    sql = "SELECT * FROM fqz_fymx_test AS f CROSS JOIN other_table AS o"
    ok, msg = SQLLogicValidator.agentic_linter(sql)
    assert ok is False
    assert "无界笛卡尔积" in msg or "安全拦截" in msg

def test_linter_blocks_join_without_on_or_using():
    sql = "SELECT * FROM fqz_all_yy_yd AS a LEFT JOIN fqz_admdvs AS d"
    ok, msg = SQLLogicValidator.agentic_linter(sql)
    assert ok is False
    assert "JOIN 语句缺失关联条件" in msg

def test_linter_allows_join_with_on():
    sql = "SELECT * FROM fqz_all_yy_yd AS a LEFT JOIN fqz_admdvs AS d ON a.admdvs = d.admdvs"
    ok, msg = SQLLogicValidator.agentic_linter(sql)
    assert ok is True
    assert msg == ""
