"""
Red tests for threshold_config_provider deep module.
Follows Red -> Green -> Refactor cycle.
"""
import pytest
from app.core.threshold.business_context_detector import BusinessContext
from app.core.threshold.threshold_intent_parser import ThresholdIntent


def test_threshold_config_provider_import_and_defaults():
    from app.core.threshold.threshold_config_provider import (
        get_threshold_config,
        get_quantile_for_degree,
        get_safety_bounds,
        get_fallback_threshold,
    )

    cfg = get_threshold_config()
    assert isinstance(cfg, dict)
    assert "business_scenarios" in cfg
    assert "anomaly_degree_mapping" in cfg

    # 异常程度映射分位数
    assert get_quantile_for_degree("HIGH") == 0.99
    assert get_quantile_for_degree("MEDIUM") == 0.95
    assert get_quantile_for_degree("LOW") == 0.90
    assert get_quantile_for_degree("UNKNOWN") == 0.95

    # 安全边界
    pharmacy_bounds = get_safety_bounds("PHARMACY")
    assert pharmacy_bounds["min"] == 50
    assert pharmacy_bounds["max"] == 30000

    inpatient_bounds = get_safety_bounds("INPATIENT")
    assert inpatient_bounds["min"] == 2000
    assert inpatient_bounds["max"] == 300000

    # 降级默认阈值
    assert get_fallback_threshold("PHARMACY") == 300
    assert get_fallback_threshold("INPATIENT") == 8000


def test_threshold_config_provider_baseline_sql():
    from app.core.threshold.threshold_config_provider import build_baseline_sql

    context = BusinessContext(
        business_type="PHARMACY",
        business_name="药店购药",
        med_type="定点药店购药",
        time_granularity="SINGLE_SETL",
        table_name="fqz_gz_jzsj_all_ql",
        confidence=0.9,
        detection_source="METADATA"
    )

    sql = build_baseline_sql(0.99, context)
    assert "quantile(0.99)" in sql
    assert "fqz_gz_jzsj_all_ql" in sql


def test_threshold_config_provider_decision_reason():
    from app.core.threshold.threshold_config_provider import build_decision_reason

    context = BusinessContext(
        business_type="PHARMACY",
        business_name="药店购药",
        med_type="定点药店购药",
        time_granularity="SINGLE_SETL",
        table_name="fqz_gz_jzsj_all_ql",
        confidence=0.9,
        detection_source="METADATA"
    )
    intent = ThresholdIntent(
        anomaly_degree="HIGH",
        user_threshold=None,
        statistical_preference="COUNT_BASED",
        confidence=0.8,
        raw_keywords=["排名最高"]
    )

    reason = build_decision_reason("DYNAMIC_QUANTILE_P99", 0.99, None, context, intent)
    assert "PHARMACY" in reason
    assert "HIGH" in reason
    assert "P99" in reason
