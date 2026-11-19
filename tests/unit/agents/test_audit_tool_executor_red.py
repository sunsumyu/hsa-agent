import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.audit_tool_executor import invoke_tools_safely


@pytest.mark.asyncio
async def test_invoke_tools_unknown_tool():
    tool_calls = [{"name": "non_existent_tool", "args": {}, "id": "call_1"}]
    tools = []
    state = {}
    
    results = await invoke_tools_safely(tool_calls, tools, state)
    assert len(results) == 1
    tc, res = results[0]
    assert tc == tool_calls[0]
    assert res["status"] == "ERROR"
    assert "Unknown tool" in res["error_message"]


@pytest.mark.asyncio
async def test_invoke_tools_probe_sql_intercepted():
    tool_calls = [{
        "name": "execute_audit_sql",
        "args": {"sql": "SELECT DISTINCT med_type FROM fqz_gz_jzsj_all_ql"},
        "id": "call_probe"
    }]
    mock_tool = MagicMock()
    mock_tool.name = "execute_audit_sql"
    mock_tool.func = None
    mock_tool.coroutine = None
    mock_tool.ainvoke = AsyncMock()

    # state 中无核心 SQL
    state = {"sql_history": []}
    
    results = await invoke_tools_safely(tool_calls, [mock_tool], state)
    assert len(results) == 1
    tc, res = results[0]
    assert res["status"] == "ERROR"
    assert "算力安全红线拦截" in res["error_message"]
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_invoke_tools_metadata_probe_exempted():
    tool_calls = [{
        "name": "execute_audit_sql",
        "args": {"sql": "DESCRIBE TABLE fqz_fymx_test"},
        "id": "call_desc"
    }]
    mock_tool = MagicMock()
    mock_tool.name = "execute_audit_sql"
    mock_tool.func = None
    mock_tool.coroutine = None
    mock_tool.ainvoke = AsyncMock(return_value={"status": "SUCCESS", "data": "columns"})

    state = {"sql_history": []}
    
    results = await invoke_tools_safely(tool_calls, [mock_tool], state)
    assert len(results) == 1
    tc, res = results[0]
    assert res.get("status") == "SUCCESS"
    mock_tool.ainvoke.assert_called_once()
