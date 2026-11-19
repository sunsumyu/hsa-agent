import pytest
import json
from langchain_core.messages import AIMessage, ToolMessage

def test_evaluate_response_fast_latency_penalty():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_response_confidence
    msg = AIMessage(
        content="这是一段非常长的分析报告内容，超过了一百个字符长度门槛，用于测试由于响应延迟过快而可能引发的幻觉惩罚机制检测用例。",
        additional_kwargs={"audit_latency_ms": 50}
    )
    score = evaluate_response_confidence(msg)
    assert score <= 0.7

def test_evaluate_response_refusal_keywords():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_response_confidence
    msg = AIMessage(content="作为一个AI助手，我无法提供该查询。")
    score = evaluate_response_confidence(msg)
    assert score <= 0.4

def test_evaluate_response_error_in_content():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_response_confidence
    msg = AIMessage(content="Execution failed due to internal error")
    score = evaluate_response_confidence(msg)
    assert score <= 0.5

def test_evaluate_response_normal():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_response_confidence
    msg = AIMessage(
        content="成功查询到违规数据共 15 条",
        additional_kwargs={"audit_latency_ms": 600},
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    )
    score = evaluate_response_confidence(msg)
    assert score == 1.0

def test_evaluate_risk_drop_delete():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_execution_risk, should_trigger_human_approval
    state = {"sql_query": "DROP TABLE fqz_fymx_test"}
    risk = evaluate_execution_risk(state)
    assert risk >= 0.9
    assert should_trigger_human_approval(state) is True

def test_evaluate_risk_normal_query():
    from app.core.guardrails.risk_confidence_evaluator import evaluate_execution_risk, should_trigger_human_approval
    state = {"sql_query": "SELECT * FROM fqz_fymx_test LIMIT 10"}
    risk = evaluate_execution_risk(state)
    assert risk < 0.6
    assert should_trigger_human_approval(state) is False

def test_should_trigger_critic_error_log():
    from app.core.guardrails.risk_confidence_evaluator import should_trigger_critic
    state = {
        "messages": [AIMessage(content="test")],
        "error_log": "Syntax error"
    }
    assert should_trigger_critic(state) is True

def test_should_trigger_critic_low_confidence():
    from app.core.guardrails.risk_confidence_evaluator import should_trigger_critic
    state = {
        "messages": [AIMessage(content="作为一个AI助手无法提供此信息")],
        "error_log": None
    }
    assert should_trigger_critic(state) is True
