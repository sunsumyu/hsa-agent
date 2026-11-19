"""
tests/unit/test_agent_interrupt_and_taskpool_red.py
===================================================
红灯测试：验证 Agent 任务打断、HITL 挂起、任务池生命周期与状态干预机制的可靠性

测试覆盖范围：
1. 图条件路由对高风险/人工审批拦截点的准确判决 (Route to HUMAN_APPROVAL)
2. HUMAN_APPROVAL 节点状态机挂起契约与 TaskPool 提交
3. TaskPoolManager 任务生命周期 (PENDING -> APPROVE / REJECT / REVISE)
4. TaskPool 防御性容错 (面对 metadata 为 None 等非标状态的健壮性)
5. 工作流拓扑结构检验 (HUMAN_APPROVAL 严格直达 END 终点以优雅停止协程)
6. 人工干预线索覆写 (⟦OVERWRITE⟧ 注入契约)
7. 会话时间旅行分叉隔离 (fork_session_thread)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from langchain_core.runnables import RunnableConfig


def test_route_sqlexec_post_triggers_human_approval():
    """验证：当触发安全红线或高危 SQL 时，路由必须精确切断执行并导向 HUMAN_APPROVAL"""
    from app.core.graph_route_coordinator import route_sqlexec_post
    
    # 模拟包含 DROP TABLE 的危险高危审计状态
    state = {
        "sql_query": "DROP TABLE fqz_fymx_test",
        "retry_count": 0,
        "error_log": None
    }
    next_node = route_sqlexec_post(state)
    assert next_node == "HUMAN_APPROVAL", f"期望路由到 HUMAN_APPROVAL，实际得到: {next_node}"


def test_workflow_human_approval_edge_leads_to_end():
    """验证：HUMAN_APPROVAL 节点必须直连 END 终点，以确保任务挂起后图执行优雅停止"""
    from app.core.agent_graph import _build_workflow_skeleton
    from langgraph.graph import END

    wf = _build_workflow_skeleton()
    # 检查 HUMAN_APPROVAL 的出边
    edges = wf.edges
    # 拓扑验证：HUMAN_APPROVAL -> __end__
    assert ("HUMAN_APPROVAL", END) in edges or any(
        src == "HUMAN_APPROVAL" and tgt == END for (src, tgt) in edges
    ), "HUMAN_APPROVAL 节点必须有指向 END 的单向终结边，保证无死循环协程"


@pytest.mark.asyncio
async def test_human_approval_node_suspension_contract():
    """验证：human_approval_node 能够正确提取 thread_id、挂起任务并生成符合契约的状态增量"""
    from app.core.agent_graph import human_approval_node
    from app.core.task_pool import TaskPoolManager

    mock_pool = TaskPoolManager()
    state = {
        "metadata": {"user_question": "查询某医院违规结算总额", "risk_score": 0.95},
        "audit_findings": ["存在无指征检查 12 条"],
        "error_log": "触发高危跨期报销红线"
    }
    config: RunnableConfig = {"configurable": {"thread_id": "audit-test-session-001"}}

    # 使用 monkeypatch 或局部替换验证
    from app.core import agent_graph
    orig_pool = agent_graph.task_pool
    try:
        agent_graph.task_pool = mock_pool
        patch = await human_approval_node(state, config)

        # 契约断言：必须声明 is_awaiting_human=True 且下一步进入 AWAITING_REVISION
        assert patch.get("is_awaiting_human") is True
        assert patch.get("next_step") == "AWAITING_REVISION"
        assert "已挂起" in patch.get("error_log", "")

        # 任务池断言：任务已进入池中
        task = mock_pool.get_task("audit-test-session-001")
        assert task is not None
        assert task["status"] == "PENDING"
        assert task["risk_score"] == 0.95
        assert task["reason"] == "触发高危跨期报销红线"
    finally:
        agent_graph.task_pool = orig_pool


def test_task_pool_lifecycle_approve_and_reject():
    """验证：动态任务池完整的生命周期管理（提交 -> 挂起 -> 审核通过/驳回打断）"""
    from app.core.task_pool import TaskPoolManager

    pool = TaskPoolManager()
    thread_1 = "thread-approval-pass"
    thread_2 = "thread-rejection-cancel"

    pool.submit_task(
        thread_1, 
        {"metadata": {"user_question": "常规核查", "risk_score": 0.4}, "audit_findings": []}, 
        "例行复核"
    )
    pool.submit_task(
        thread_2, 
        {"metadata": {"user_question": "全量重构表", "risk_score": 0.99}, "audit_findings": ["高危操作"]}, 
        "危险审计请求"
    )

    pending_list = pool.list_all_pending()
    assert len(pending_list) == 2
    assert {t["thread_id"] for t in pending_list} == {thread_1, thread_2}

    # 1. 模拟人工审核打断与彻底终止 (REJECT)
    pool.complete_task(thread_2, action="REJECT", feedback="操作风险过高，驳回执行")
    task_2 = pool.get_task(thread_2)
    assert task_2["status"] == "COMPLETED"
    assert task_2["action"] == "REJECT"
    assert task_2["feedback"] == "操作风险过高，驳回执行"
    assert "completed_at" in task_2

    # 验证 pending 列表已移出被终止的任务
    remaining_pending = pool.list_all_pending()
    assert len(remaining_pending) == 1
    assert remaining_pending[0]["thread_id"] == thread_1

    # 2. 模拟人工审核通过 (APPROVE)
    pool.complete_task(thread_1, action="APPROVE", feedback="准予继续执行")
    assert len(pool.list_all_pending()) == 0


def test_task_pool_defensive_against_none_metadata():
    """验证：TaskPool 面对畸形状态 (例如 metadata 为 None 或 audit_findings 为 None) 的健壮性"""
    from app.core.task_pool import TaskPoolManager

    pool = TaskPoolManager()
    malformed_state = {
        "metadata": None,  # 易引发 .get('user_question') 的 AttributeError
        "audit_findings": None
    }
    
    # 确保在极端非标状态下提交不引发崩溃
    # 注意：如果源码中使用了 state.get('metadata', {}).get(...)，在 metadata=None 时会抛 AttributeError
    try:
        pool.submit_task("malformed-thread", malformed_state, "测试非标状态")
        task = pool.get_task("malformed-thread")
        assert task is not None
        assert task["risk_score"] == 0.0
    except AttributeError as e:
        pytest.fail(f"TaskPoolManager.submit_task 防御不足，在 metadata 为 None 时抛出了异常: {e}")


def test_findings_overwrite_formatting():
    """验证：人工干预线索覆盖格式化协议 (⟦OVERWRITE⟧)"""
    from app.core.graph_state_orchestrator import format_findings_overwrite

    # 列表形式输入
    findings_list = ["线索 A: 异常跨院就诊", "线索 B: 超频次报销"]
    formatted_list = format_findings_overwrite(findings_list)
    assert len(formatted_list) == 1
    assert formatted_list[0].startswith("⟦OVERWRITE⟧")
    assert "线索 A: 异常跨院就诊\n线索 B: 超频次报销" in formatted_list[0]

    # 单字符串形式输入
    formatted_str = format_findings_overwrite("直接覆盖结论")
    assert formatted_str == ["⟦OVERWRITE⟧直接覆盖结论"]


@pytest.mark.asyncio
async def test_intervene_session_findings_nonexistent():
    """验证：对不存在的会话进行人工干预时，必须优雅返回 error 状态而非异常溃退"""
    from app.core.graph_state_orchestrator import intervene_session_findings

    mock_executor = AsyncMock()
    mock_executor.aget_state.return_value = None

    result = await intervene_session_findings(
        session_id="ghost-session-999",
        findings=["人工纠偏线索"],
        executor=mock_executor
    )
    assert result["status"] == "error"
    assert "不存在" in result["message"]


@pytest.mark.asyncio
async def test_intervene_session_findings_success_flow():
    """验证：对挂起会话进行人工干预成功时，通过 aupdate_state 安全注入 ⟦OVERWRITE⟧ 数据"""
    from app.core.graph_state_orchestrator import intervene_session_findings

    mock_executor = AsyncMock()
    # 模拟已有状态快照
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"messages": [], "findings": ["旧的错误线索"]}
    mock_executor.aget_state.return_value = mock_snapshot
    mock_executor.aupdate_state = AsyncMock()

    result = await intervene_session_findings(
        session_id="active-session-123",
        findings=["人工纠偏的正确线索"],
        executor=mock_executor
    )
    assert result["status"] == "success"
    mock_executor.aupdate_state.assert_awaited_once()
    call_args = mock_executor.aupdate_state.call_args[0]
    config_arg, state_update = call_args
    assert config_arg == {"configurable": {"thread_id": "active-session-123"}}
    assert "⟦OVERWRITE⟧" in state_update["findings"][0]


@pytest.mark.asyncio
async def test_fork_session_thread_isolation():
    """验证：打断后支持时间旅行分叉克隆，目标线程继承状态切片"""
    from app.core.graph_state_orchestrator import fork_session_thread

    mock_executor = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"audit_findings": ["冻结的历史证据点"], "step": 3}
    mock_executor.aget_state.return_value = mock_snapshot
    mock_executor.aupdate_state = AsyncMock()

    res = await fork_session_thread(
        source_session="parent-frozen-session",
        target_session="branch-trial-session",
        executor=mock_executor
    )
    assert res["status"] == "success"
    assert res["targetSession"] == "branch-trial-session"
    mock_executor.aupdate_state.assert_awaited_once_with(
        {"configurable": {"thread_id": "branch-trial-session"}},
        {"audit_findings": ["冻结的历史证据点"], "step": 3}
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
