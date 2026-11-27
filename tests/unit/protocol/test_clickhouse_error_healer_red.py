"""
Red tests for clickhouse_error_healer deep module.
Follows Red -> Green -> Refactor cycle.
"""
import pytest
import asyncio


def test_clickhouse_error_healer_import_and_code6():
    from app.core.protocol.clickhouse_error_healer import heal_clickhouse_execution_error

    sql_with_tab = "SELECT toDateTime('2024-01-01\t12:00:00') FROM test_table"
    err = "Code: 6. DB::Exception: CANNOT_PARSE_TEXT"

    healed = heal_clickhouse_execution_error(sql_with_tab, err)
    assert healed is not None
    assert "\t" not in healed
    assert "2024-01-01 12:00:00" in healed


def test_clickhouse_error_healer_code215():
    from app.core.protocol.clickhouse_error_healer import heal_clickhouse_execution_error

    sql = "SELECT dept_name, count(*) FROM fqz_gz_jzsj_all_ql GROUP BY setl_id"
    err = "Code: 215. DB::Exception: Column 'dept_name' is not under aggregate function and not in GROUP BY"

    healed = heal_clickhouse_execution_error(sql, err)
    assert healed is not None
    assert "GROUP BY setl_id, dept_name" in healed


def test_clickhouse_error_healer_code184():
    from app.core.protocol.clickhouse_error_healer import heal_clickhouse_execution_error

    sql = "SELECT count(*) AS setl_id FROM fqz_gz_jzsj_all_ql WHERE setl_id > 10"
    err = "Code: 184. DB::Exception: Aggregate function is found in WHERE in query"

    healed = heal_clickhouse_execution_error(sql, err)
    assert healed is not None
    assert "AS count_setl_id" in healed or "WHERE fqz_gz_jzsj_all_ql.setl_id" in healed or "setl_id" in healed


@pytest.mark.asyncio
async def test_execute_with_auto_heal_success():
    from app.core.protocol.clickhouse_error_healer import execute_with_auto_heal

    call_count = 0

    async def mock_query(sql: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Code: 215. Column 'bad_col' is not under aggregate function and not in GROUP BY")
        return [{"ok": 1}]

    initial_sql = "SELECT bad_col, count(*) FROM t GROUP BY id"
    records, final_sql = await execute_with_auto_heal(mock_query, initial_sql)

    assert call_count == 2
    assert records == [{"ok": 1}]
    assert "bad_col" in final_sql
