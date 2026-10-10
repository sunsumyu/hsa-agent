import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator

def test_negative_compliance_eval_passes_when_report_proves_zero_findings():
    report = """
    ## 核心核查结论
    经对结算主表 2,500 笔记录进行全量穿透排查，未检出满足异常记录。
    数据总量覆盖：全表共覆盖结算记录 2,500 笔，时间跨度 2024-03 至 2024-10。
    物理底表仅包含 1 家医疗机构，物理上无法构成跨机构就诊事实。
    """
    res = AuditMetricEvaluator.evaluate(
        eval_type="negative_compliance",
        gt_count=0,
        gt_sum=0.0,
        db_rows=[],
        report_text=report,
        key_entities=["2500", "未检出"]
    )
    assert res.recall_pct == 100.0
    assert res.precision_pct == 100.0
    assert res.f1_score == 1.0

def test_negative_compliance_eval_fails_when_hallucinated_records_returned():
    # 模拟底表实际为 0，但模型幻觉检出 10 条伪造记录且报告声称违规
    fake_rows = [{"psn_no": "P001", "fee": 100.0}] * 10
    report = "发现 10 笔严重违规套取医保基金嫌疑！"
    res = AuditMetricEvaluator.evaluate(
        eval_type="negative_compliance",
        gt_count=0,
        gt_sum=0.0,
        db_rows=fake_rows,
        report_text=report
    )
    assert res.recall_pct == 0.0
    assert res.precision_pct == 0.0
    assert res.f1_score == 0.0

if __name__ == "__main__":
    test_negative_compliance_eval_passes_when_report_proves_zero_findings()
    test_negative_compliance_eval_fails_when_hallucinated_records_returned()
    print("ALL TESTS PASSED SUCCESSFULLY!")
