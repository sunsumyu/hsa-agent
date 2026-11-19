"""
tests/unit/agents/test_evidence_extractor_deep_red.py
=====================================================
红灯测试：审计证据提取与截断策略/核心SQL仲裁解耦
验证 EvidenceTruncationPolicy 与 CoreSqlResolver
"""

import json
import pytest

from app.agents.evidence_truncation_policy import truncate_evidence_data
from app.agents.core_sql_resolver import resolve_core_audit_sql
from app.agents.tool_evidence_extractor import ToolEvidenceExtractor, tool_evidence_extractor


def test_truncate_evidence_data_structured_with_totals():
    """测试结构化数据集超限时注入首行宏观统计并保全有效 JSON"""
    data = [
        {"psn_no": f"P{i:03d}", "item_fee": 100.0, "hosp": "定点医院A"}
        for i in range(100)
    ]
    truncated_str = truncate_evidence_data(data, max_chars=300)
    parsed = json.loads(truncated_str)
    
    # 验证采样并保全宏观信息
    assert len(parsed) < 100
    meta = parsed[0]
    assert meta["is_truncated"] is True
    assert meta["total_records"] == 100
    assert meta["total_amount"] == 10000.0


def test_truncate_evidence_data_text():
    """测试纯文本数据超限截断保护"""
    long_text = "ABC" * 100
    truncated_str = truncate_evidence_data(long_text, max_chars=50)
    assert len(truncated_str.split("...")[0]) <= 50
    assert "WARNING: Data truncated due to excessive length" in truncated_str


def test_resolve_core_audit_sql_prioritizes_metrics():
    """测试核心 SQL 解析器在多个 SQL 中优先选择带有金额/度量计算的核心查询"""
    sqls = [
        "SELECT count(*) FROM fqz_gz_jzsj_all_ql",  # 探针查询
        "SELECT * FROM fqz_fymx_test WHERE gend = '1' LIMIT 10",  # 辅助样本查询
        "SELECT fixmedins_name, ROUND(SUM(det_item_fee_sumamt), 2) AS total_fee FROM fqz_fymx_test GROUP BY fixmedins_name"  # 核心业务度量查询
    ]
    core_sql = resolve_core_audit_sql(sqls)
    assert "ROUND(SUM(det_item_fee_sumamt)" in core_sql
    assert "fixmedins_name" in core_sql


def test_resolve_core_audit_sql_fallback_when_all_probes():
    """测试当历史 SQL 全部为探针查询时的保底回退策略"""
    sqls = [
        "SELECT count(*) FROM fqz_gz_jzsj_all_ql",
        "SELECT count(DISTINCT psn_no) FROM fqz_gz_jzsj_all_ql"
    ]
    core_sql = resolve_core_audit_sql(sqls)
    assert core_sql == sqls[-1]


def test_tool_evidence_extractor_facade_compatibility():
    """测试 ToolEvidenceExtractor 门面委派正确性"""
    extractor = ToolEvidenceExtractor(max_chars=400)
    data = [{"psn_no": "P01", "fee": 500.0}]
    res = extractor.truncate_data(data)
    assert "500" in res

    tool_call = {"id": "c1", "name": "execute_audit_sql"}
    tool_res = {
        "status": "SUCCESS",
        "sql_logic": "SELECT psn_no, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 10000 GROUP BY psn_no",
        "data": [{"psn_no": "P01", "sum": 50000}]
    }
    processed = extractor.process([(tool_call, tool_res)], {"sql_history": []})
    assert "GROUP BY psn_no" in processed.sql_query
    assert "50000" in processed.raw_data
