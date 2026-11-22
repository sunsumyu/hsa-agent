# -*- coding: utf-8 -*-
"""
tests/unit/core/test_execution_subgraph_replay.py
==================================================
[全链路重放回归测试] 端到端复现 execution_engine_node 的真实执行。

与 test_execution_subgraph_red.py 的分层差异（测试金字塔）：
- red 契约测试: mock 掉 coder_agent.execute / compiled subgraph.ainvoke，
  验证子图拓扑、状态契约与门面投影接缝；
- 本重放测试: 仅 mock 「LLM 调用」与「工具物理执行」两个外设，
  Gate 2/Gate 3、协议归一化、证据提取、子图路由与门面过滤全部真实运行，
  复现「CODER → GATE → CRITIC 自愈闭环」的真实行为（可捕获单测 mock 盲区，
  如曾存活于成功路径的 audit_intent 悬空引用 NameError）。

场景 1: Round1 恒假 SQL 被 Gate 2 拦截 → CRITIC 自愈 → Round2 合规 SQL 成功交付
场景 2: 持续恒假 SQL → 逃生舱熔断，优雅退出并保留失败诊断
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch
from langchain_core.messages import AIMessage, HumanMessage


# ── 预录数据 (与离线重放调试脚本 tmp/replay_execution_subgraph.py 同源) ──

USER_QUESTION = "帮我汇总一下2024年医保就诊结算的总体情况，做个资金对账。"
BAD_SQL = (
    "SELECT setl_id, medfee_sumamt FROM fqz_fymx_test "
    "WHERE gend NOT LIKE '1%' AND gend NOT LIKE '2%'"
)
GOOD_SQL = (
    "SELECT toDate(setl_time) AS setl_date, count(*) AS visit_cnt, "
    "sum(medfee_sumamt) AS total_fee "
    "FROM fqz_gz_jzsj_all_ql GROUP BY setl_date ORDER BY setl_date"
)
MOCK_ROWS = [
    {"setl_date": "2024-01-05", "visit_cnt": 128, "total_fee": 92314.5},
    {"setl_date": "2024-01-06", "visit_cnt": 96, "total_fee": 77102.0},
    {"setl_date": "2024-01-07", "visit_cnt": 152, "total_fee": 110233.75},
]
CRITIC_TEXT = (
    "【诊断】你的 SQL 对性别字段 gend 同时排除了全部合法取值('1'和'2')，"
    "谓词恒假导致结果必然为空集。请移除全排斥的 NOT LIKE 条件，"
    "改为按结算日期 GROUP BY 的全量聚合统计口径。"
)


@pytest.fixture(autouse=True)
def setup_di():
    from app.core.container import ServiceProvider
    from app.core.bootstrap import register_services
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def _make_coder_tool_call(sql: str, call_id: str) -> dict:
    return {"name": "execute_audit_sql", "args": {"sql": sql}, "id": call_id, "type": "tool_call"}


def _install_llm_replay(coder_sqls):
    """按调用序回放 coder SQL 序列；critic 固定诊断文本。返回 (chat替身, 工具执行替身, 调用流水)。"""
    calls = []
    seq = {"coder": 0}

    async def fake_chat(*args, **kwargs):
        role = kwargs.get("role") or (args[0] if args else "unknown")
        if role == "coder":
            idx = seq["coder"]
            seq["coder"] += 1
            sql = coder_sqls[idx] if idx < len(coder_sqls) else coder_sqls[-1]
            resp = AIMessage(content="", tool_calls=[_make_coder_tool_call(sql, f"call_coder_{idx + 1}")])
        else:
            resp = AIMessage(content=CRITIC_TEXT)
        calls.append((role, resp))
        return resp

    async def fake_invoke_tools(tool_calls, tools, state, is_probe_fn=None):
        results = []
        for tc in (tool_calls or []):
            sql = (tc.get("args") or {}).get("sql", "")
            results.append((tc, {
                "status": "SUCCESS",
                "sql_logic": sql,
                "data": MOCK_ROWS,
                "trace_hint": f"mock-clickhouse: {len(MOCK_ROWS)} rows",
            }))
        return results

    return AsyncMock(side_effect=fake_chat), AsyncMock(side_effect=fake_invoke_tools), calls


async def _run_engine(coder_sqls):
    """在仅隔离外设的前提下，端到端驱动 execution_engine_node。"""
    from app.core.subgraphs.execution_subgraph import execution_engine_node
    from app.agents.coder_agent import AuditCoderAgent
    from app.skills.sql.sql_validator import sql_validator

    chat_mock, tools_mock, calls = _install_llm_replay(coder_sqls)

    parent_state = {
        "tasks": ["任务1: 按结算日期汇总全院结算总体情况"],
        "methodology": "按 toDate(setl_time) 维度 GROUP BY 聚合结算单数与总费用，进行全院资金对账。",
        "metadata": {"user_question": USER_QUESTION, "user_id": "replay_admin"},
        "session_id": "replay-test-001",
        "messages": [HumanMessage(content=USER_QUESTION)],
        "execution_trace": ["parent_entry"],
    }

    # noinspection PyUnresolvedReferences
    with patch("app.core.llm_provider.LLMProvider.chat", new=chat_mock), \
         patch("app.agents.audit_tool_executor.invoke_tools_safely", new=tools_mock), \
         patch("app.agents.coder_agent.execute_fast_route_bypass",
               AsyncMock(return_value=SimpleNamespace(
                   handled=False, fallback_to_llm=False, state_update={}))), \
         patch.object(sql_validator, "agentic_linter", lambda sql: (True, "")), \
         patch.object(AuditCoderAgent, "max_retries", new_callable=PropertyMock, return_value=5):
        output = await execution_engine_node(parent_state, None)
    return output, calls


@pytest.mark.asyncio
async def test_replay_self_healing_loop_end_to_end():
    """场景 1: Gate 2 拦截 → CRITIC 自愈 → Round2 合规 SQL 成功交付（全链路真实运行）"""
    output, calls = await _run_engine([BAD_SQL, GOOD_SQL])

    # 真实 LLM 边界调用序列: coder 失败 → critic 诊断 → coder 修正
    assert [role for role, _ in calls] == ["coder", "critic", "coder"]

    # 核心交付物: 修正后的合规 SQL 成功取证
    assert output["sql_validated"] is True
    assert output["sql_query"] == GOOD_SQL
    assert output["final_sql"] == GOOD_SQL, "sql_query 与 final_sql 必须双键互通"
    assert "2024-01-05" in str(output["raw_data"]), "模拟 ClickHouse 结果必须进入证据链"

    # 真实子图循环足迹: v0 失败 → critic 反思 → v2 成功 (coder_exec 序号来自真实自愈轮次)
    trace = output["execution_trace"]
    assert "parent_entry" in trace
    assert any(t.startswith("coder_exec_v0") for t in trace)
    assert any(t.startswith("critic_reflect") for t in trace)
    assert any(t.startswith("coder_exec_v2") for t in trace)

    # 信息隐藏: 真实子图运行后的私有字段严禁泄漏至父图
    for leaked in ("sql_history", "retry_count", "messages", "internal_critic_log"):
        assert leaked not in output, f"私有字段 {leaked} 泄漏至父图"


@pytest.mark.asyncio
async def test_replay_escape_hatch_on_persistent_contradiction():
    """场景 2: 持续恒假 SQL → 逃生舱熔断，保留失败诊断优雅退出（杜绝父图死循环）"""
    output, calls = await _run_engine([BAD_SQL, BAD_SQL])

    assert output["sql_validated"] is False
    assert "恒假" in str(output["error_log"]), "最后一次 Gate 2 拦截诊断必须透传给父图"
    assert [role for role, _ in calls] == ["coder", "critic", "coder"], "熔断前应恰好 2 轮 coder + 1 轮 critic"

    trace = output["execution_trace"]
    assert sum(t.startswith("coder_exec") for t in trace) == 2
    assert sum(t.startswith("critic_reflect") for t in trace) == 1
