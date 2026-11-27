"""
tests/unit/skills/test_analysis_operator_runner_red.py
======================================================
Red tests for analysis_operator_runner deep module.
Tests:
- execute_rule_operator (validation, not found, sql failure, success, exception)
- execute_anomaly_operator (validation, not found, sql failure, success, exception)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.skills.rules.analysis_operator_runner import (
    execute_rule_operator,
    execute_anomaly_operator,
)


@pytest.mark.asyncio
async def test_execute_rule_operator_empty_id():
    res = await execute_rule_operator("")
    assert "Error: rule_id is required." in res


@pytest.mark.asyncio
async def test_execute_rule_operator_not_found():
    mock_engine = MagicMock()
    mock_engine.get_rule_sql.return_value = None

    res = await execute_rule_operator("UNKNOWN_RULE_XYZ", rule_eng=mock_engine)
    data = json.loads(res)
    assert "未找到匹配的审计算子" in data["report"]
    assert data["evidence_count"] == 0


@pytest.mark.asyncio
async def test_execute_rule_operator_sql_blocked():
    mock_engine = MagicMock()
    mock_engine.get_rule_sql.return_value = "SELECT 1"
    mock_sql_exec = AsyncMock(return_value="执行失败: 语法错误")

    res = await execute_rule_operator("GENDER", rule_eng=mock_engine, sql_executor=mock_sql_exec)
    data = json.loads(res)
    assert "物理引擎执行受阻" in data["report"]
    assert data["evidence_count"] == 0


@pytest.mark.asyncio
async def test_execute_rule_operator_success():
    mock_engine = MagicMock()
    mock_engine.get_rule_sql.return_value = "SELECT * FROM test"
    mock_engine.format_violation_report.return_value = "发现 2 条性别冲突"
    mock_sql_exec = AsyncMock(return_value=[{"id": 1}, {"id": 2}])

    res = await execute_rule_operator("GENDER", rule_eng=mock_engine, sql_executor=mock_sql_exec)
    data = json.loads(res)
    assert data["evidence_count"] == 2
    assert "发现 2 条性别冲突" in data["report"]
    assert len(data["raw_evidence"]) == 2
    assert "[规则引擎]" in data["trace_hint"]
    assert data["sql_logic"] == "SELECT * FROM test"


@pytest.mark.asyncio
async def test_execute_anomaly_operator_empty_id():
    res = await execute_anomaly_operator("")
    assert "Error: algorithm_id is required." in res


@pytest.mark.asyncio
async def test_execute_anomaly_operator_success():
    mock_detector = MagicMock()
    mock_detector.get_algorithm_sql.return_value = "SELECT * FROM vix"
    mock_detector.format_anomaly_report.return_value = "发现 3 条离群指标"
    mock_sql_exec = AsyncMock(return_value=[{"k": "a"}, {"k": "b"}, {"k": "c"}])

    res = await execute_anomaly_operator("VIX", detector=mock_detector, sql_executor=mock_sql_exec)
    data = json.loads(res)
    assert data["evidence_count"] == 3
    assert "发现 3 条离群指标" in data["report"]
    assert "[异常算法]" in data["trace_hint"]
