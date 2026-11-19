"""
tests/unit/security/test_data_masker_red.py
============================================
[SPEC-227 / Matt Pocock Deep Module] 医保数据隐私与 PII 脱敏深模块测试 (红灯先行)
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from app.core.security.data_masker import (
    apply_pii_masking,
    sanitize_audit_content,
    mask_audit_data,
)


def test_apply_pii_masking_id_card():
    """测试身份证号码脱敏：保留前6后4"""
    text = "参保人身份证为 110101199003072345 进行就医。"
    masked = apply_pii_masking(text)
    assert "110101********2345" in masked
    assert "110101199003072345" not in masked


def test_apply_pii_masking_phone():
    """测试手机号码脱敏：保留前3后4"""
    text = "联系电话：13812345678"
    masked = apply_pii_masking(text)
    assert "138****5678" in masked
    assert "13812345678" not in masked


def test_apply_pii_masking_name():
    """测试患者姓名脱敏：姓名：张三 -> 姓名：张*"""
    text = "患者：李四在门诊就医，姓名：王五办理结算。"
    masked = apply_pii_masking(text)
    assert "李*" in masked or "李**" in masked
    assert "王*" in masked or "王**" in masked


def test_sanitize_audit_content_removes_sql_in_normal_msgs():
    """测试在非最终报告消息中清除冗余 SQL 调试代码块"""
    msgs = [
        AIMessage(content="分析执行结果：```sql\nSELECT * FROM test\n```\n患者身份证为 110101199003072345")
    ]
    cleaned = sanitize_audit_content(msgs)
    res_content = cleaned[0].content
    assert "[SQL EXEC_TRACE_REMOVED]" in res_content
    assert "110101********2345" in res_content


def test_sanitize_audit_content_preserves_sql_in_final_report():
    """测试在最终医保专项稽核报告中保留 SQL 代码块以保障可审计性"""
    report_text = "# 📋 医保专项稽核报告\n```sql\nSELECT * FROM test\n```\n患者电话 13912345678"
    msgs = [AIMessage(content=report_text)]
    cleaned = sanitize_audit_content(msgs)
    res_content = cleaned[0].content
    assert "SELECT * FROM test" in res_content
    assert "139****5678" in res_content


def test_mask_audit_data_dict_list():
    """测试结构化字典列表数据打码"""
    data = [
        {
            "psn_name": "姓名：张三丰",
            "tel": "13800001111",
            "psn_no": "110101199003072345",
            "hospital": "测试三甲医院",
        }
    ]
    masked = mask_audit_data(data)
    assert "138****1111" in masked[0]["tel"]
    assert "110101********2345" in masked[0]["psn_no"]
    assert masked[0]["hospital"] == "测试三甲医院"
