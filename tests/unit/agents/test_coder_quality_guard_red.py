"""
tests/unit/agents/test_coder_quality_guard_red.py
=================================================
测试驱动开发 (TDD) 红灯测试:
验证 CoderAgent 质量门控与执行前后自愈评估深模块 (coder_quality_guard)
"""

import pytest
from app.agents.coder_quality_guard import (
    check_pre_execution_gate,
    check_post_execution_gate,
    PreExecutionGateResult,
    PostExecutionGateResult,
)


def test_pre_execution_gate_no_sql_tool():
    tool_calls = [{"name": "calculator", "args": {"expression": "1+1"}}]
    res = check_pre_execution_gate(tool_calls, state={})
    assert res.passed is True
    assert res.error is None
    assert res.sql_arg == ""


def test_pre_execution_gate_valid_sql(monkeypatch):
    # 模拟 QualityGate 语义校验通过
    from app.core.context.gates import QualityGate
    monkeypatch.setattr(QualityGate, "validate_sql_semantics", lambda state, sql: {"passed": True})

    tool_calls = [{"name": "execute_audit_sql", "args": {"sql": "SELECT count(*) FROM fqz_gz_jzsj_all_ql"}}]
    res = check_pre_execution_gate(tool_calls, state={})
    assert res.passed is True
    assert res.sql_arg == "SELECT count(*) FROM fqz_gz_jzsj_all_ql"


def test_pre_execution_gate_invalid_sql(monkeypatch):
    # 模拟 QualityGate 拦截违规 SQL
    from app.core.context.gates import QualityGate
    monkeypatch.setattr(
        QualityGate,
        "validate_sql_semantics",
        lambda state, sql: {"passed": False, "error": "禁止跨域查询"},
    )

    tool_calls = [{"name": "execute_audit_sql", "args": {"sql": "SELECT * FROM forbidden_tbl"}}]
    res = check_pre_execution_gate(tool_calls, state={})
    assert res.passed is False
    assert "禁止跨域查询" in res.error
    assert res.sql_arg == "SELECT * FROM forbidden_tbl"


def test_post_execution_gate_no_sql():
    res = check_post_execution_gate(sql="", methodology="", raw_data=[], intent=None)
    assert res.passed is True
    assert res.error_feedback is None


def test_post_execution_gate_linter_failed(monkeypatch):
    from app.skills.sql.sql_validator import sql_validator
    monkeypatch.setattr(sql_validator, "agentic_linter", lambda sql: (False, "语法缺少 FROM"))

    res = check_post_execution_gate(
        sql="SELECT 1",
        methodology="测试",
        raw_data=[{"a": 1}],
        intent=None,
    )
    assert res.passed is False
    assert "【SQL 逻辑审查拦截】" in res.error_feedback


def test_post_execution_gate_reflection_eval(monkeypatch):
    from app.skills.sql.sql_validator import sql_validator
    from app.core.booster import booster
    from app.core.reflection.audit_reflection_engine import AuditReflectionEngine, ReflectionResult

    # Linter 和数值通过
    monkeypatch.setattr(sql_validator, "agentic_linter", lambda sql: (True, ""))
    monkeypatch.setattr(booster, "parse_table_to_rows", lambda raw: [])
    monkeypatch.setattr(booster, "detect_anomalous_consistency", lambda rows: None)

    # 反思自愈引擎判定需要重试
    monkeypatch.setattr(
        AuditReflectionEngine,
        "evaluate_execution",
        lambda sql, row_count, intent, error_msg: ReflectionResult(
            needs_retry=True,
            diagnostic_feedback="结果行数为 0，建议放宽阈值",
        ),
    )

    res = check_post_execution_gate(
        sql="SELECT * FROM table WHERE amt > 99999999",
        methodology="排查超大额",
        raw_data=[],
        intent=None,
    )
    assert res.passed is False
    assert "建议放宽阈值" in res.error_feedback
