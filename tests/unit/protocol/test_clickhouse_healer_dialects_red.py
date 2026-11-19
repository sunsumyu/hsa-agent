import pytest
import sqlglot
from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer


def test_healer_repairs_mysql_datediff_and_ifnull():
    sql = "SELECT DATEDIFF(end_date, start_date) AS diff_days, IFNULL(amt, 0) AS safe_amt FROM fqz_fymx_test"
    healed = ClickHouseDialectHealer.heal(sql)
    assert "dateDiff('day', start_date, end_date)" in healed
    assert "ifNull(amt, 0)" in healed


def test_healer_repairs_mysql_year_month_and_curdate():
    sql = "SELECT YEAR(setl_time) AS y, MONTH(setl_time) AS m, CURDATE() AS today_dt FROM fqz_fymx_test"
    healed = ClickHouseDialectHealer.heal(sql)
    assert "toYear(setl_time)" in healed
    assert "toMonth(setl_time)" in healed
    assert "today()" in healed


def test_healer_repairs_group_concat():
    sql = "SELECT GROUP_CONCAT(hilist_name) AS drugs FROM fqz_fymx_test"
    healed = ClickHouseDialectHealer.heal(sql)
    assert "arrayStringConcat(groupUniqArray(hilist_name)" in healed


def test_healer_heal_expression_method_exists():
    expr = sqlglot.parse_one("SELECT DATEDIFF(end_date, start_date) FROM fqz_fymx_test", read="clickhouse")
    healed_expr = ClickHouseDialectHealer.heal_expression(expr)
    sql_out = healed_expr.sql(dialect="clickhouse")
    assert "dateDiff('day', start_date, end_date)" in sql_out
