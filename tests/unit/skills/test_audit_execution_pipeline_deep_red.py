"""
tests/unit/skills/test_audit_execution_pipeline_deep_red.py
==========================================================
[Matt Pocock Deep Module Red Test] 审计规则/算法执行流水线与证据规整解耦测试
"""

import pytest
from unittest.mock import MagicMock
from app.skills.rules.audit_execution_pipeline import (
    AuditExecutionPipeline,
    audit_execution_pipeline,
)


def test_pipeline_resolve_query_sql_rule_hit():
    """验证从规则引擎命中 SQL 时正确返回 (sql, False)"""
    pipeline = AuditExecutionPipeline()
    mock_rules = MagicMock()
    mock_rules.get_rule_sql.return_value = "SELECT * FROM fqz_fymx WHERE 1=1"
    mock_anomaly = MagicMock()

    sql, is_anomaly = pipeline.resolve_query_sql(
        target_id="GENDER_CONFLICT",
        extra_filters={"gend": "1"},
        rule_engine_inst=mock_rules,
        anomaly_detector_inst=mock_anomaly,
    )

    assert sql == "SELECT * FROM fqz_fymx WHERE 1=1"
    assert is_anomaly is False
    mock_rules.get_rule_sql.assert_called_once_with("GENDER_CONFLICT", extra_filters={"gend": "1"})
    mock_anomaly.get_algorithm_sql.assert_not_called()


def test_pipeline_resolve_query_sql_anomaly_fallback():
    """验证规则引擎未命中时自动降级到统计异常检测引擎并返回 (sql, True)"""
    pipeline = AuditExecutionPipeline()
    mock_rules = MagicMock()
    mock_rules.get_rule_sql.return_value = None
    mock_anomaly = MagicMock()
    mock_anomaly.get_algorithm_sql.return_value = "SELECT fixmedins_name, stddev(medfee) FROM fqz_fymx GROUP BY 1"

    sql, is_anomaly = pipeline.resolve_query_sql(
        target_id="DYNAMIC_VIX_SCAN",
        extra_filters={"year": "2024"},
        rule_engine_inst=mock_rules,
        anomaly_detector_inst=mock_anomaly,
    )

    assert sql.startswith("SELECT fixmedins_name")
    assert is_anomaly is True
    mock_rules.get_rule_sql.assert_called_once()
    mock_anomaly.get_algorithm_sql.assert_called_once_with("DYNAMIC_VIX_SCAN", extra_filters={"year": "2024"})


def test_pipeline_normalize_evidence_result():
    """验证不同类型的底层执行结果被统一规整"""
    pipeline = AuditExecutionPipeline()

    # 1. 成功列表
    ok, err, data = pipeline.normalize_evidence_result([{"id": "A1"}])
    assert ok is True
    assert err is None
    assert data == [{"id": "A1"}]

    # 2. 结构化错误字典
    ok, err, data = pipeline.normalize_evidence_result({"status": "ERROR", "error_message": "Table not found"})
    assert ok is False
    assert "SQL Execution Failed: Table not found" in err
    assert data == []

    # 3. 拦截字符串
    ok, err, data = pipeline.normalize_evidence_result("执行失败: 触发安全熔断")
    assert ok is False
    assert "Execution blocked: 执行失败: 触发安全熔断" in err
    assert data == []

    # 4. None 或非集合
    ok, err, data = pipeline.normalize_evidence_result(None)
    assert ok is True
    assert err is None
    assert data == []


def test_pipeline_format_evidence_report_and_payload():
    """验证多态报告生成与最终证据信封组装"""
    pipeline = AuditExecutionPipeline()

    mock_rules = MagicMock()
    mock_rules.format_violation_report.return_value = "【规则违规】命中 2 条"
    mock_anomaly = MagicMock()
    mock_anomaly.format_anomaly_report.return_value = "【算法异常】变异系数超标"

    # 业务规则分支
    report_rule = pipeline.format_evidence_report(
        target_id="GENDER_CONFLICT",
        raw_data=[{"id": 1}, {"id": 2}],
        is_anomaly=False,
        rule_engine_inst=mock_rules,
        anomaly_detector_inst=mock_anomaly,
    )
    assert report_rule == "【规则违规】命中 2 条"
    mock_rules.format_violation_report.assert_called_once()

    # 异常算法分支
    report_anomaly = pipeline.format_evidence_report(
        target_id="DYNAMIC_VIX_SCAN",
        raw_data=[{"id": 1}],
        is_anomaly=True,
        rule_engine_inst=mock_rules,
        anomaly_detector_inst=mock_anomaly,
    )
    assert report_anomaly == "【算法异常】变异系数超标"
    mock_anomaly.format_anomaly_report.assert_called_once()

    # 信封组装
    payload = pipeline.assemble_audit_payload(
        report_text=report_rule,
        raw_data=[{"id": 1}, {"id": 2}],
        methodology="性别冲突核查",
        sql="SELECT 1",
        is_anomaly=False,
    )
    assert payload["evidence_count"] == 2
    assert payload["report"] == "【规则违规】命中 2 条"
    assert payload["methodology"] == "性别冲突核查"
    assert payload["sql_logic"] == "SELECT 1"
    assert "[Rule Engine]" in payload["trace_hint"]
