# -*- coding: utf-8 -*-
"""
tests/unit/core/test_execution_subgraph_red.py
==============================================
[TDD Red -> Green] 数据执行与自愈子图 (Execution Subgraph) 契约测试
Driven by: Matt Pocock Deep Module & Seam Isolation Principles

测试项：
1. 子图私有状态契约 (ExecutionSubState) 隔离性验证
2. 一次性执行成功直通路径 (Coder -> Gate -> END)
3. 局部自愈循环 (Coder -> Gate 拦截 -> Critic 诊断 -> Coder 修正 -> END)
4. 最大重试逃生舱 (Escape Hatch) 熔断机制，杜绝顶层死循环
5. 结果向父图投影收敛 (Clean Output Seam)，零局部脏字段泄漏
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig


@pytest.fixture(autouse=True)
def setup_di():
    from app.core.container import ServiceProvider
    from app.core.bootstrap import register_services
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def test_subgraph_state_isolation():
    """断言 1: 子图拥有独立的状态定义，包含内部私有临时变量"""
    from app.core.subgraphs.execution_subgraph import ExecutionSubState
    annotations = ExecutionSubState.__annotations__

    # 必须具备的内部自愈变量
    assert "retry_count" in annotations
    assert "max_retries" in annotations
    assert "sql_history" in annotations
    # 必须具备的交付物
    assert "final_sql" in annotations or "sql_query" in annotations
    assert "raw_data" in annotations
    assert "sql_validated" in annotations


@pytest.mark.asyncio
async def test_execution_subgraph_direct_success():
    """断言 2: 一次性执行成功直通路径，不触发 Critic 反思"""
    from app.core.subgraphs.execution_subgraph import build_execution_subgraph

    subgraph = build_execution_subgraph(max_retries=2)
    assert subgraph is not None

    mock_coder_res = {
        "sql_query": "SELECT count(*) FROM fqz_fymx_test WHERE drug_name LIKE '%保妇康栓%'",
        "raw_data": "[{'count': 217}]",
        "sql_validated": True,
        "error_log": None,
    }

    with patch("app.agents.coder_agent.coder_agent.execute", new_callable=AsyncMock) as mock_exec, \
         patch("app.core.context.gates.QualityGate.validate_result_matching", return_value={"passed": True}) as mock_gate, \
         patch("app.agents.reflection_agent.reflection_agent.reflect", new_callable=AsyncMock) as mock_reflect:

        mock_exec.return_value = mock_coder_res

        initial_state = {
            "tasks": ["排查保妇康栓费用明细"],
            "methodology": "ClickHouse 物理汇总",
            "metadata": {"user_question": "全省各级开具保妇康栓费用"},
            "session_id": "test-session-001",
            "messages": [],
            "retry_count": 0,
            "max_retries": 2,
        }

        result = await subgraph.ainvoke(initial_state)

        assert result["sql_validated"] is True
        assert result["raw_data"] == "[{'count': 217}]"
        assert mock_exec.call_count == 1
        assert mock_reflect.call_count == 0, "一次性成功的任务严禁调用 Critic 浪费算力"


@pytest.mark.asyncio
async def test_execution_subgraph_self_healing_loop():
    """断言 3: 首次执行失败触发 Critic 自愈诊断，次轮修正成功后平滑退出"""
    from app.core.subgraphs.execution_subgraph import build_execution_subgraph

    subgraph = build_execution_subgraph(max_retries=2)

    # 第一轮失败，第二轮成功
    fail_res = {
        "sql_query": "SELECT * FROM broken_table",
        "raw_data": "",
        "sql_validated": False,
        "error_log": "Table broken_table doesn't exist",
    }
    success_res = {
        "sql_query": "SELECT count(*) FROM fqz_fymx_test",
        "raw_data": "[{'count': 217}]",
        "sql_validated": True,
        "error_log": None,
    }

    critic_feedback = {
        "error_log": "[CRITIC 反馈] 请修正表名为 fqz_fymx_test",
        "messages": [AIMessage(content="请修正表名")],
        "retry_count": 1,
    }

    with patch("app.agents.coder_agent.coder_agent.execute", new_callable=AsyncMock) as mock_exec, \
         patch("app.agents.reflection_agent.reflection_agent.reflect", new_callable=AsyncMock) as mock_reflect, \
         patch("app.core.context.gates.QualityGate.validate_result_matching", return_value={"passed": True}):

        mock_exec.side_effect = [fail_res, success_res]
        mock_reflect.return_value = critic_feedback

        initial_state = {
            "tasks": ["排查保妇康栓"],
            "methodology": "ClickHouse 物理汇总",
            "metadata": {"user_question": "全省开具保妇康栓"},
            "session_id": "test-session-002",
            "messages": [],
            "retry_count": 0,
            "max_retries": 2,
        }

        result = await subgraph.ainvoke(initial_state)

        # 验证局部自愈成功
        assert result["sql_validated"] is True
        assert result["raw_data"] == "[{'count': 217}]"
        assert mock_exec.call_count == 2
        assert mock_reflect.call_count == 1


@pytest.mark.asyncio
async def test_parent_projection_clean_seam():
    """断言 4: [深模块接缝] execution_engine_node 对父图交付时必须做投影收敛，杜绝局部脏数据泄漏"""
    from app.core.subgraphs.execution_subgraph import execution_engine_node

    parent_state = {
        "metadata": {"user_question": "排查保妇康栓"},
        "tasks": ["任务1"],
        "methodology": "方法论",
        "session_id": "parent-session-123",
        "messages": [],
        "retry_count": 0,
        # 父图已有业务字段
        "audit_findings": [],
    }

    mock_sub_res = {
        "sql_query": "SELECT 1",
        "raw_data": "data",
        "sql_validated": True,
        "execution_trace": ["t1", "t2"],
        # 子图内部临时字段
        "internal_critic_log": "私有诊断日志",
        "sql_history": ["SELECT 1", "SELECT 2"],
    }

    with patch("app.core.subgraphs.execution_subgraph.compiled_execution_subgraph.ainvoke", new_callable=AsyncMock) as mock_sub:
        mock_sub.return_value = mock_sub_res

        output_patch = await execution_engine_node(parent_state, RunnableConfig())

        # 断言父图拿到的是干净的受敛字典
        assert "sql_query" in output_patch
        assert "raw_data" in output_patch
        assert "sql_validated" in output_patch
        assert "execution_trace" in output_patch

        # 严禁将子图私有内部字段泄露回父图
        assert "internal_critic_log" not in output_patch
        assert "sql_history" not in output_patch


@pytest.mark.asyncio
async def test_execution_subgraph_escape_hatch():
    """断言 5: 达到最大重试次数时逃生舱熔断，优雅退出至 END，防止死循环"""
    from app.core.subgraphs.execution_subgraph import build_execution_subgraph

    subgraph = build_execution_subgraph(max_retries=1)

    persistent_fail = {
        "sql_query": "SELECT * FROM never_exists",
        "raw_data": "",
        "sql_validated": False,
        "error_log": "Persistent table error",
    }
    critic_guidance = {
        "error_log": "[CRITIC] Guidance",
        "retry_count": 1,
    }

    with patch("app.agents.coder_agent.coder_agent.execute", new_callable=AsyncMock) as mock_exec, \
         patch("app.agents.reflection_agent.reflection_agent.reflect", new_callable=AsyncMock) as mock_reflect:

        mock_exec.return_value = persistent_fail
        mock_reflect.return_value = critic_guidance

        initial_state = {
            "tasks": ["排查保妇康栓"],
            "methodology": "ClickHouse 物理汇总",
            "metadata": {"user_question": "全省开具保妇康栓"},
            "session_id": "test-session-003",
            "messages": [],
            "retry_count": 0,
            "max_retries": 1,
        }

        result = await subgraph.ainvoke(initial_state)

        # 验证逃生舱熔断：仅重试 1 次即熔断退出，返回失败状态给父图
        assert result["sql_validated"] is False
        assert result["error_log"] is not None
        # 第1次执行 -> 失败 -> critic诊断 (retry_count=1) -> 第2次执行 (retry_count=1) -> 失败 -> 触发 escape hatch 退出
        assert mock_exec.call_count == 2
        assert mock_reflect.call_count == 1


@pytest.mark.asyncio
async def test_sqlexec_node_subgraph_feature_flag_routing():
    """断言 6: [平滑迁移特性开关] sqlexec_node 在 use_execution_subgraph=True 时无缝分流至子图"""
    from app.core.config import settings
    from app.core.agent_graph import sqlexec_node

    parent_state = {
        "metadata": {"user_question": "排查保妇康栓"},
        "tasks": ["任务1"],
        "methodology": "方法论",
        "session_id": "routing-session-001",
        "messages": [],
        "retry_count": 0,
    }

    # 1. 默认 use_execution_subgraph = False 时走向经典 Coder 流程
    with patch.object(settings, "use_execution_subgraph", False), \
         patch("app.agents.coder_agent.coder_agent.execute", new_callable=AsyncMock) as mock_coder:
        mock_coder.return_value = {"sql_query": "SELECT 1", "raw_data": "ok", "sql_validated": True}
        res_legacy = await sqlexec_node(parent_state, RunnableConfig())
        assert mock_coder.call_count == 1
        assert res_legacy["sql_query"] == "SELECT 1"

    # 2. 开启 use_execution_subgraph = True 时无缝分流至 execution_engine_node
    with patch.object(settings, "use_execution_subgraph", True), \
         patch("app.core.subgraphs.execution_subgraph.execution_engine_node", new_callable=AsyncMock) as mock_engine:
        mock_engine.return_value = {"sql_query": "SELECT 2", "raw_data": "subgraph_ok", "sql_validated": True}
        res_subgraph = await sqlexec_node(parent_state, RunnableConfig())
        assert mock_engine.call_count == 1
        assert res_subgraph["sql_query"] == "SELECT 2"
        assert res_subgraph["raw_data"] == "subgraph_ok"
