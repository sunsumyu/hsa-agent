"""
tests/unit/reporting/test_findings_section_builder_red.py
=========================================================
[SPEC-227 / Matt Pocock Deep Module] 报告核查数据发现与表格排版深模块测试 (红灯先行)
"""

import pytest
from app.reporting.findings_section_builder import build_findings_section


def test_build_findings_section_restricted():
    """测试受限执行场景下的防御提示"""
    res = build_findings_section(
        raw_data=[],
        total_amount=0.0,
        finding_count=0,
        is_restricted=True,
    )
    assert "## 三、核查数据发现" in res
    assert "由于 SQL 执行受限，本次未检出任何明细数据。" in res


def test_build_findings_section_empty_data():
    """测试正常无异常记录场景"""
    res = build_findings_section(
        raw_data=[],
        total_amount=0.0,
        finding_count=0,
        is_restricted=False,
    )
    assert "在当前核查口径下，未检出符合条件的异常记录。" in res


def test_build_findings_section_markdown_table_and_desensitization():
    """测试标准 Markdown 表格排版与敏感字段过滤脱敏"""
    raw_data = [
        {"psn_no": "P01", "phone": "13800138000", "fee": 120.50, "hospital": "测试三甲医院"},
        {"psn_no": "P02", "phone": "13900139000", "fee": 300.00, "hospital": "测试二甲医院"},
    ]
    res = build_findings_section(
        raw_data=raw_data,
        total_amount=420.50,
        finding_count=2,
        is_restricted=False,
        max_evidence_rows=10,
        sensitive_fields={"phone"},
    )
    assert "| psn_no | fee | hospital |" in res
    # 敏感字段 phone 及其明细手机号被彻底移除
    assert "phone" not in res
    assert "13800138000" not in res
    assert "¥120.50" in res
    assert "¥420.50" in res


def test_build_findings_section_all_sensitive_fallback():
    """测试当全量字段均为敏感字段时表头保留且单元格脱敏为 ***"""
    raw_data = [{"phone": "13800138000"}]
    res = build_findings_section(
        raw_data=raw_data,
        total_amount=0.0,
        finding_count=1,
        sensitive_fields={"phone"},
    )
    assert "| phone |" in res
    assert "***" in res
    assert "13800138000" not in res


def test_build_findings_section_list_format_preference():
    """测试用户偏好 LIST 无序列表格式输出"""
    raw_data = [
        {"psn_no": "P01", "fee": 100.0, "hospital": "仁济医院"}
    ]
    res = build_findings_section(
        raw_data=raw_data,
        total_amount=100.0,
        finding_count=1,
        format_preference="LIST",
    )
    assert "- 序号 1：" in res
    assert "**psn_no**: P01" in res
