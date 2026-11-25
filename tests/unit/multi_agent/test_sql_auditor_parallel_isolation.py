import asyncio
import json

import pytest

from app.multi_agent.contracts import GraphClueArtifact, SubTaskSpec
from app.multi_agent.sql_auditor_agent import SQLAuditorSubagent


@pytest.mark.asyncio
async def test_parallel_sql_subtasks_run_concurrently_without_context_bleed():
    seen_states = []

    async def fake_coder_exec(state, config):
        seen_states.append(dict(state))
        await asyncio.sleep(0.05)
        q = state["current_turn_query"]
        if "节育" in q:
            rows = [{"psn_no": "P1", "det_item_fee_sumamt": 840.0}]
            sql = "SELECT psn_no, det_item_fee_sumamt FROM fqz_fymx_test WHERE gend = '1'"
        else:
            rows = [{"psn_no": "P2", "det_item_fee_sumamt": -29.7}]
            sql = "SELECT psn_no, det_item_fee_sumamt FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0"
        return {
            "sql_query": sql,
            "raw_data": json.dumps(rows, ensure_ascii=False),
            "sql_validated": True,
            "error_log": None,
        }

    subtasks = [
        SubTaskSpec(subtask_id="s1", focus_title="节育器核查", query_instruction="排查男性宫内节育器"),
        SubTaskSpec(subtask_id="s2", focus_title="退费核查", query_instruction="排查负数退费明细"),
    ]
    auditor = SQLAuditorSubagent(coder_executor=fake_coder_exec)
    artifacts = await auditor.run_parallel(subtasks, session_id="sess-1")

    assert len(artifacts) == 2
    assert artifacts[0].total_amount == 840.0
    assert artifacts[0].row_count == 1
    assert artifacts[0].validated is True
    assert artifacts[1].total_amount == -29.7
    assert artifacts[1].row_count == 1
    assert artifacts[1].validated is True
    assert len(seen_states[0]["messages"]) == 1
    assert len(seen_states[1]["messages"]) == 1
    assert seen_states[0]["current_turn_query"] != seen_states[1]["current_turn_query"]
    assert seen_states[0]["session_id"] == "sess-1:s1"
    assert seen_states[1]["session_id"] == "sess-1:s2"
    assert seen_states[0]["metadata"]["user_question"] == seen_states[0]["current_turn_query"]
    assert seen_states[1]["metadata"]["user_question"] == seen_states[1]["current_turn_query"]


@pytest.mark.asyncio
async def test_sql_auditor_injects_sideload_temp_table_or_relational_fallback():
    captured_queries = []
    captured_temp_tables = []

    async def fake_coder_exec(state, config):
        captured_queries.append(state["current_turn_query"])
        captured_temp_tables.append(state.get("temp_table"))
        return {"sql_query": "SELECT 1", "raw_data": "[]", "sql_validated": True, "error_log": None}

    auditor = SQLAuditorSubagent(coder_executor=fake_coder_exec)
    subtask = SubTaskSpec(subtask_id="g1", focus_title="团伙核算", query_instruction="统计团伙涉案总金额")

    clue_ok = GraphClueArtifact(succeeded=True, temp_table="fqz_temp_sl_abcd1234", entity_count=6)
    await auditor.run_subtask(subtask, session_id="s1", graph_clue=clue_ok)
    assert "fqz_temp_sl_abcd1234" in captured_queries[-1]
    assert captured_temp_tables[-1] == "fqz_temp_sl_abcd1234"

    clue_deg = GraphClueArtifact(succeeded=False, degraded_to_relational=True)
    await auditor.run_subtask(subtask, session_id="s1", graph_clue=clue_deg)
    assert "GROUP BY tel" in captured_queries[-1]
    assert captured_temp_tables[-1] is None


@pytest.mark.asyncio
async def test_parallel_sql_subtasks_isolate_exceptions_per_subtask():
    async def flaky_coder_exec(state, config):
        if "BOOM" in state["current_turn_query"]:
            raise RuntimeError("ClickHouse connection reset")
        rows = [{"psn_no": "P9", "det_item_fee_sumamt": 125.5}]
        return {
            "sql_query": "SELECT psn_no, det_item_fee_sumamt FROM fqz_fymx_test",
            "raw_data": json.dumps(rows, ensure_ascii=False),
            "sql_validated": True,
            "error_log": None,
        }

    subtasks = [
        SubTaskSpec(subtask_id="ok-1", focus_title="正常核查1", query_instruction="核查正常样本1"),
        SubTaskSpec(subtask_id="fail-1", focus_title="异常核查", query_instruction="触发 BOOM 异常"),
        SubTaskSpec(subtask_id="ok-2", focus_title="正常核查2", query_instruction="核查正常样本2"),
    ]
    auditor = SQLAuditorSubagent(coder_executor=flaky_coder_exec)
    artifacts = await auditor.run_parallel(subtasks, session_id="sess-err")

    assert len(artifacts) == 3
    assert artifacts[0].subtask_id == "ok-1"
    assert artifacts[0].validated is True
    assert artifacts[0].total_amount == 125.5

    assert artifacts[1].subtask_id == "fail-1"
    assert artifacts[1].validated is False
    assert "ClickHouse connection reset" in (artifacts[1].error or "")
    assert artifacts[1].row_count == 0
    assert artifacts[1].total_amount == 0.0

    assert artifacts[2].subtask_id == "ok-2"
    assert artifacts[2].validated is True
    assert artifacts[2].total_amount == 125.5
