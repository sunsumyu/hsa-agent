"""
tests/test_audit_metric_evaluator.py
====================================
根据 Matt Pocock TDD 原则编写的评测指标深模块契约测试：
覆盖常规数据审计、负数退费异常明细、零发现合规基线、UNION ALL 汇总行去重等边界条件。
"""

import pytest
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator


def test_eval_exact_records_simple_list():
    """测试常规明细行结果：12 条离群记录"""
    db_rows = [{"fixmedins_name": f"Hosp_{i}", "det_item_fee_sumamt": 1200.0} for i in range(12)]
    res = AuditMetricEvaluator.evaluate(
        eval_type="exact_records",
        gt_count=12,
        gt_sum=14815.0,
        db_rows=db_rows
    )
    assert res.tp == 12
    assert res.fp == 0
    assert res.fn == 0
    assert res.recall_pct == 100.0
    assert res.precision_pct == 100.0


def test_eval_negative_refund_does_not_confuse_cnt_with_count():
    """
    针对 QA-SCOPE-03 核心回归测试：
    明细行中包含项目开药数量 'cnt': -21.0, -6.0，
    绝不能将其误当成聚合计数字段，而应该识别为 2 条明细行！
    """
    db_rows = [
        {"setl_id": "S1", "hilist_name": "戊酸雌二醇片", "det_item_fee_sumamt": -29.7, "cnt": -21.0},
        {"setl_id": "S2", "hilist_name": "保妇康栓", "det_item_fee_sumamt": -4.72, "cnt": -6.0}
    ]
    res = AuditMetricEvaluator.evaluate(
        eval_type="exact_records",
        gt_count=2,
        gt_sum=-34.42,
        db_rows=db_rows
    )
    assert res.det_count == 2
    assert res.tp == 2
    assert res.fp == 0
    assert res.fn == 0
    assert res.recall_pct == 100.0
    assert res.precision_pct == 100.0


def test_eval_union_all_summary_deduplication():
    """
    针对 QA-SCOPE-01 核心回归测试：
    SQL 使用 UNION ALL 输出了 1 行全库总计 (4613) + 若干明细行 (总和 4613)，
    评测器应该识别出总计行，提取 4613，绝不能重复累加为 9226！
    """
    db_rows = [
        {"sort_key": 0, "drug_name": "【全库总计汇总】", "record_count": 4613, "total_amount": 100000.0},
        {"sort_key": 1, "drug_name": "缩宫素注射液", "record_count": 3000, "total_amount": 60000.0},
        {"sort_key": 1, "drug_name": "黄体酮胶囊", "record_count": 1613, "total_amount": 40000.0},
    ]
    res = AuditMetricEvaluator.evaluate(
        eval_type="exact_records",
        gt_count=4613,
        gt_sum=100000.0,
        db_rows=db_rows
    )
    assert res.det_count == 4613
    assert res.tp == 4613
    assert res.fp == 0
    assert res.recall_pct == 100.0
    assert res.precision_pct == 100.0


def test_eval_zero_findings_compliance_report():
    """
    针对 QA-SCOPE-06 核心回归测试：
    GT 违规数为 0。SQL 查了底表元数据产生了 1 行统计行，
    但审计报告明确给出“未发现违规”的合规结论，
    评测器应判定完全命中零发现合规基线！
    """
    db_rows = [{"total_records": 2500, "distinct_patients": 100}]
    report = "### 审计结论：经排查2024年数据未发现同人同日同院反复结算的拆单骗保行为，总体合规。"
    res = AuditMetricEvaluator.evaluate(
        eval_type="zero_findings",
        gt_count=0,
        gt_sum=0.0,
        db_rows=db_rows,
        report_text=report
    )
    assert res.tp == 1
    assert res.fp == 0
    assert res.fn == 0
    assert res.recall_pct == 100.0
    assert res.precision_pct == 100.0
