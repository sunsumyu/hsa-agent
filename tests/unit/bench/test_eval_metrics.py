import pytest
import sys
import os

# 导入基准评测模块中的评估函数
sys.path.insert(0, os.path.abspath("."))
from scratch.run_7metrics_bench import evaluate_recall_and_precision

def test_evaluate_handles_grouped_settlement_counts():
    # 场景: Agent 按 3 个日期 GROUP BY，字段名为 setl_count，总笔数累加是 2500
    case = {
        "ground_truth": {
            "eval_type": "exact_records",
            "expected_count": 2500,
            "expected_sum": 348640.30
        }
    }
    db_rows = [
        {"setl_date": "2024-03-06", "setl_count": 1000, "total_amt": 150000.0},
        {"setl_date": "2024-04-11", "setl_count": 800, "total_amt": 100000.0},
        {"setl_date": "2024-04-15", "setl_count": 700, "total_amt": 98640.3}
    ]
    res = evaluate_recall_and_precision(case, "SELECT toDate(setl_time) AS setl_date ...", db_rows, "测试报告")
    # 评测引擎必须能够自动识别计数类列，并求和累加为 2500，计算召回率 100%，而非错误地判定为 3 行
    assert res["det_count"] == 2500
    assert res["recall_pct"] == 100.0
    assert res["precision_pct"] == 100.0

def test_evaluate_handles_dynamic_count_column_detection():
    # 场景: 字段名未列入静态枚举，如 cases_num、distinct_bills 等
    case = {
        "ground_truth": {
            "eval_type": "exact_records",
            "expected_count": 50,
            "expected_sum": 1000.0
        }
    }
    db_rows = [
        {"dept": "内科", "cases_num": 30},
        {"dept": "外科", "cases_num": 20}
    ]
    res = evaluate_recall_and_precision(case, "SELECT dept, count(*) as cases_num ...", db_rows, "测试报告")
    assert res["det_count"] == 50
    assert res["recall_pct"] == 100.0
