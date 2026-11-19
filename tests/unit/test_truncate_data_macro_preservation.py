import json
import pytest
from app.agents.tool_evidence_extractor import ToolEvidenceExtractor
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator

def test_truncate_data_under_limit():
    """验证未超限的小数据集原样返回，不破坏数据原始格式"""
    extractor = ToolEvidenceExtractor(max_chars=2000)
    data = [
        {"psn_no": "P01", "fee": 100.0},
        {"psn_no": "P02", "fee": 200.0}
    ]
    res_str = extractor.truncate_data(data)
    parsed = json.loads(res_str)
    assert len(parsed) == 2
    assert "total_records" not in parsed[0]

def test_truncate_data_oversized_preserves_macro_totals():
    """验证当大数据集触发安全截断时，注入宏观汇总行，使得下游评估器依然能 100% 提取出真实检出总条数和总金额"""
    # 设置一个较小的预算，强制触发截断
    extractor = ToolEvidenceExtractor(max_chars=500)
    
    # 模拟 300 条违规记录，每条金额 50 元，总金额 15,000 元
    large_dataset = [
        {"psn_no": f"PATIENT_{i:04d}", "det_item_fee_sumamt": 50.0, "hospital": "测试三甲医院"}
        for i in range(300)
    ]
    
    res_str = extractor.truncate_data(large_dataset)
    parsed = json.loads(res_str)
    
    # 截断后采样保留的记录数应远小于 300，但首行必须是宏观汇总
    assert len(parsed) < 300
    meta_row = parsed[0]
    assert meta_row.get("is_truncated") is True
    assert meta_row.get("total_records") == 300
    assert meta_row.get("total_amount") == 15000.0
    
    # 验证下游 AuditMetricEvaluator 是否能从该截断数据中完美对账提取出宏观 300 条和 15,000 元
    det_count, det_sum = AuditMetricEvaluator.extract_totals(parsed)
    assert det_count == 300, f"宏观检出总数应为 300，实测为 {det_count}"
    assert abs(det_sum - 15000.0) < 1e-2, f"宏观总金额应为 15000，实测为 {det_sum}"
