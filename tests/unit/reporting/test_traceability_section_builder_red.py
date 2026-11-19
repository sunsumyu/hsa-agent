"""
tests/unit/reporting/test_traceability_section_builder_red.py
=============================================================
测试驱动开发 (TDD) 红灯测试:
验证审计报告第五章风险评估与第六章审计可追溯凭证生成深模块 (traceability_section_builder)
"""

import time
import pytest
from app.reporting.traceability_section_builder import (
    build_risk_section,
    build_traceability_section,
    resolve_admin_name,
    calculate_risk_level,
    generate_evidence_fingerprint,
)


def test_build_risk_section():
    # 测试高风险评级
    high_risk_md = build_risk_section(risk_level="高", total_amount=1234567.89, finding_count=150)
    assert "## 五、风险评级" in high_risk_md
    assert "🔴 **高风险**" in high_risk_md
    assert "¥1,234,567.89" in high_risk_md
    assert "150 条" in high_risk_md

    # 测试中风险评级
    med_risk_md = build_risk_section(risk_level="中", total_amount=50000.0, finding_count=20)
    assert "🟡 **中风险**" in med_risk_md
    assert "¥50,000.00" in med_risk_md

    # 测试低风险评级
    low_risk_md = build_risk_section(risk_level="低", total_amount=100.0, finding_count=1)
    assert "🟢 **低风险**" in low_risk_md

    # 测试未知风险等级
    other_risk_md = build_risk_section(risk_level="未知", total_amount=0.0, finding_count=0)
    assert "⚪ **未知风险**" in other_risk_md


def test_build_traceability_section_empty():
    assert build_traceability_section(None) == ""
    assert build_traceability_section({}) == ""


def test_build_traceability_section_full():
    timestamp = 1718000000  # 2024-06-10 14:13:20 (local)
    metadata = {
        "trace_id": "tr-abc-123456",
        "audit_model_id": "DeepSeek-V3",
        "audit_latency_ms": 125.67,
        "audit_timestamp": timestamp,
    }
    
    md = build_traceability_section(metadata)
    assert "## 六、审计可追溯性凭证" in md
    assert "| 物理算力节点 | `DeepSeek-V3` |" in md
    assert "| 全链路 TraceID | `tr-abc-123456` |" in md
    assert "| 推理总耗时 | 125.7 ms |" in md
    assert "ARGUS-" in md
    assert "⚠️ **审计申明**" in md
    assert "| 执行时间戳 |" in md


def test_resolve_admin_name():
    # 缺省兜底
    assert resolve_admin_name(None) == "Argus 智能审计中心"
    assert resolve_admin_name("") == "Argus 智能审计中心"
    
    # 区县级前缀与已知代码
    assert resolve_admin_name("DIST_310104") == "【区县级】徐汇区医疗保障局"
    assert resolve_admin_name("CITY_310100") == "【地市级】上海市医保中心 (地市级)"
    assert resolve_admin_name("PROV_310000") == "【省级】上海市医疗保障局"
    assert resolve_admin_name("310115") == "浦东新区医疗保障局"
    
    # 未知代码兜底
    assert resolve_admin_name("999999") == "行政代码 999999 审计组"
    assert resolve_admin_name("DIST_999999") == "【区县级】行政代码 999999 审计组"


def test_calculate_risk_level():
    # 默认高风险：金额>=50000 或 数量>=10
    assert calculate_risk_level(total_amount=50000.0, finding_count=0) == "高"
    assert calculate_risk_level(total_amount=0.0, finding_count=10) == "高"
    
    # 默认中风险：金额>=10000 或 数量>=3
    assert calculate_risk_level(total_amount=10000.0, finding_count=1) == "中"
    assert calculate_risk_level(total_amount=500.0, finding_count=3) == "中"
    
    # 默认低风险
    assert calculate_risk_level(total_amount=9999.0, finding_count=2) == "低"

    # 自定义阈值
    custom_thresholds = {
        "high": {"min_amount": 500, "min_count": 5},
        "medium": {"min_amount": 100, "min_count": 2},
    }
    assert calculate_risk_level(600, 1, custom_thresholds) == "高"
    assert calculate_risk_level(50, 3, custom_thresholds) == "中"
    assert calculate_risk_level(50, 1, custom_thresholds) == "低"


def test_generate_evidence_fingerprint():
    fp1 = generate_evidence_fingerprint("tr-001", "model-a", 1000)
    fp2 = generate_evidence_fingerprint("tr-001", "model-a", 1000)
    fp3 = generate_evidence_fingerprint("tr-002", "model-a", 1000)
    assert fp1.startswith("ARGUS-")
    assert fp1 == fp2  # 确定性哈希
    assert fp1 != fp3  # 区分度
