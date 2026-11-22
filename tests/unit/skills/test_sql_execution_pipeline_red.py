"""
tests/unit/skills/test_sql_execution_pipeline_red.py
====================================================
Red unit tests for sql_execution_pipeline deep module.
Tests:
- Probe query hijacking via SchemaRegistry
- SQLGuardian safety & expected table rejection
- Tenant administrative hierarchy isolation injection
- Successful execution & USP SkillResponse packaging
- Error healing retry mechanism
- Infrastructure unreachable error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.skills.sql.sql_execution_pipeline import execute_audit_sql_pipeline
from app.infra.db_conn import SqlExecError


class MockClient:
    def __init__(self, query_fn):
        self.query = query_fn


@pytest.mark.asyncio
async def test_probe_query_hijacking_describe():
    # DESCRIBE fqz_gz_jzsj_all_ql should be intercepted by SchemaRegistry
    res = await execute_audit_sql_pipeline("DESCRIBE fqz_gz_jzsj_all_ql", return_raw=True)
    assert isinstance(res, list)
    assert len(res) > 0
    assert any(col.get("column_name") == "psn_no" for col in res)


@pytest.mark.asyncio
async def test_probe_query_hijacking_usp_response():
    res = await execute_audit_sql_pipeline("SHOW COLUMNS FROM fqz_fymx_test", return_raw=False)
    assert isinstance(res, dict)
    assert res.get("status") == "SUCCESS"
    assert "Schema 注册表" in res.get("logic_summary", "")
    assert isinstance(res.get("data"), list)


@pytest.mark.asyncio
async def test_sql_guardian_rejection_forbidden_table():
    # Querying non-existent or forbidden table without mock
    res = await execute_audit_sql_pipeline("SELECT * FROM invalid_hallucinated_table")
    assert isinstance(res, dict)
    assert res.get("status") == "ERROR"
    assert "error_message" in res


@pytest.mark.asyncio
async def test_sql_execution_success_and_usp_format():
    records = [{"psn_no": "P001", "medfee_sumamt": 120.5}]
    mock_query = MagicMock(return_value=records)
    mock_client = MockClient(mock_query)

    res = await execute_audit_sql_pipeline(
        "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' AND gend = '1'",
        return_raw=False,
        client_getter=lambda: mock_client
    )

    assert isinstance(res, dict)
    assert res.get("status") == "SUCCESS"
    assert res.get("affected_rows") == 1
    assert res.get("security_verified") is True
    assert len(res.get("data")) == 1


@pytest.mark.asyncio
async def test_sql_execution_return_raw():
    records = [{"psn_no": "P001", "medfee_sumamt": 120.5}]
    mock_query = MagicMock(return_value=records)
    mock_client = MockClient(mock_query)

    res = await execute_audit_sql_pipeline(
        "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' AND gend = '1'",
        return_raw=True,
        client_getter=lambda: mock_client
    )

    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]["psn_no"] == "P001"


@pytest.mark.asyncio
async def test_sql_execution_infra_error_handling():
    def _fail_query(sql):
        raise SqlExecError("Connection refused: 无法建立与 ClickHouse 的物理连接 (host: localhost, port: 8123)")

    mock_client = MockClient(_fail_query)

    res = await execute_audit_sql_pipeline(
        "SELECT count(*) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'",
        return_raw=False,
        client_getter=lambda: mock_client
    )

    assert isinstance(res, dict)
    assert res.get("status") == "ERROR"
    assert res.get("is_infra_error") is True
    assert "ClickHouse 数据库未启动或不可达" in res.get("error_message")


@pytest.mark.asyncio
async def test_sql_execution_auto_healing_retry():
    calls = []

    def _healed_query(sql):
        calls.append(sql)
        if len(calls) == 1:
            # First call fails with DB::Exception: Missing columns: 'start_date'
            raise SqlExecError("Code: 47. DB::Exception: Missing columns: 'start_date' while processing query")
        return [{"cnt": 42}]

    mock_client = MockClient(_healed_query)

    # healing rule returns a modified sql to trigger retry
    healed_sql = "SELECT count(*) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'"
    with patch("app.core.protocol.clickhouse_error_healer.heal_clickhouse_execution_error", return_value=healed_sql):
        res = await execute_audit_sql_pipeline(
            "SELECT count(*), toDate(start_date) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'",
            return_raw=True,
            client_getter=lambda: mock_client
        )
        assert len(calls) == 2
        assert res == [{"cnt": 42}]

