import pytest
from langchain_core.messages import ToolMessage, AIMessage

def test_route_planner_post_synthesis():
    from app.orchestration.graph_route_coordinator import route_planner_post
    state = {"metadata": {"synthesis_done": True}}
    assert route_planner_post(state) == "CONSOLIDATOR"

def test_route_planner_post_error():
    from app.orchestration.graph_route_coordinator import route_planner_post
    state = {"error_log": "Gate 1: Intent check failed"}
    assert route_planner_post(state) == "CRITIC"

def test_route_planner_post_normal():
    from app.orchestration.graph_route_coordinator import route_planner_post
    state = {}
    assert route_planner_post(state) == "SQLEXEC"

def test_route_critic_post_intent_error():
    from app.orchestration.graph_route_coordinator import route_critic_post
    state = {"error_log": "意图理解不一致"}
    assert route_critic_post(state) == "PLANNER"

def test_route_critic_post_exec_error():
    from app.orchestration.graph_route_coordinator import route_critic_post
    state = {"error_log": "SQL syntax error near SELECT"}
    assert route_critic_post(state) == "SQLEXEC"

def test_route_sqlexec_post_fast_route():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    state = {"metadata": {"fast_route_id": "route_1"}}
    assert route_sqlexec_post(state) == "CONSOLIDATOR"

def test_route_sqlexec_post_evidence_secured():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    state = {
        "sql_validated": True,
        "raw_data": "[{'count': 10}]",
        "error_log": None
    }
    assert route_sqlexec_post(state) == "CONSOLIDATOR"

def test_route_sqlexec_post_tool_call_loop():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "execute_query", "args": {}}])
    state = {
        "messages": [ai_msg],
        "retry_count": 0
    }
    assert route_sqlexec_post(state) == "SQLEXEC"

def test_route_sqlexec_post_error_retry():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    state = {
        "error_log": "Timeout error",
        "retry_count": 0
    }
    assert route_sqlexec_post(state) == "CRITIC"

def test_route_sqlexec_post_error_retry_exceeded():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    state = {
        "error_log": "Timeout error",
        "retry_count": 1
    }
    # 超过 MAX_RETRIES (1)，降级走向 CONSOLIDATOR
    assert route_sqlexec_post(state) == "CONSOLIDATOR"


def test_route_aligner_post_direct_reporter():
    from app.orchestration.graph_route_coordinator import route_aligner_post
    assert route_aligner_post({"metadata": {"synthesis_done": True}}) == "REPORTER"
    assert route_aligner_post({"metadata": {}}) == "PLANNER"


def test_route_planner_post_circuit_breaker():
    from app.orchestration.graph_route_coordinator import route_planner_post
    state = {"error_log": "Gate 1: Intent check failed", "plan_retry_count": 2}
    assert route_planner_post(state, max_retries=1) == "CONSOLIDATOR"


def test_route_critic_post_circuit_breaker():
    from app.orchestration.graph_route_coordinator import route_critic_post
    assert route_critic_post({"error_log": "意图理解不一致", "plan_retry_count": 2}, max_retries=1) == "CONSOLIDATOR"
    assert route_critic_post({"error_log": "SQL syntax error", "sql_retry_count": 2}, max_retries=1) == "CONSOLIDATOR"


def test_route_sqlexec_post_tool_step_limit():
    from app.orchestration.graph_route_coordinator import route_sqlexec_post
    ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "execute_query", "args": {}}])
    state = {
        "messages": [ai_msg],
        "retry_count": 0,
        "tool_step_count": 5,
    }
    assert route_sqlexec_post(state, max_retries=1, max_tool_steps=5) == "CONSOLIDATOR"
