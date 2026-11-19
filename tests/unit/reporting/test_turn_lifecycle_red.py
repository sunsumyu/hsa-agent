import pytest
from app.reporting.turn_lifecycle import (
    extract_key_entities,
    resolve_format_preference,
    create_turn_commit_patch,
)


def test_extract_key_entities():
    """测试从数据列表中准确提取并去重核心审计实体"""
    raw_data = [
        {"fixmedins_name": "省第一人民医院", "psn_name": "张三", "det_item_fee": 100},
        {"fixmedins_name": "省第一人民医院", "hilist_name": "益母草颗粒"}, # 重复医院名应去重
        {"medins_name": "市第三中医院", "psn_name": "李四"},
    ]
    entities = extract_key_entities(raw_data)
    assert entities == ["省第一人民医院", "张三", "益母草颗粒", "李四", "市第三中医院"]



def test_resolve_format_preference_from_profile_and_notes():
    """测试报表格式偏好的优先级解析：profile > notes"""
    # 场景 1: 来自 user_profile
    state1 = {
        "metadata": {"user_profile": {"format": "TABLE"}}
    }
    assert resolve_format_preference(state1) == "TABLE"

    # 场景 2: 来自 audit_notes 中的偏好记录
    state2 = {
        "metadata": {},
        "audit_notes": [
            "一般便签",
            "【偏好设置】请使用无序列表输出最终审计结论",
        ]
    }
    assert resolve_format_preference(state2) == "LIST"

    # 场景 3: 默认无偏好
    assert resolve_format_preference({}) is None


def test_create_turn_commit_patch():
    """测试生成轮末不可变发现与标准化状态重置包"""
    state = {
        "metadata": {"turn": 1, "target_tables": ["fqz_fymx_test"]},
        "accumulated_findings": [],
        "sql_query": "SELECT * FROM fqz_fymx_test"
    }
    patch = create_turn_commit_patch(
        state=state,
        user_query="查询违规情况",
        summary_conclusion="发现违规结算 5 条",
        hard_count=5,
        hard_sum=1250.0,
        key_entities=["省第一人民医院"]
    )

    # 验证新追加的 finding
    findings = patch["accumulated_findings"]
    assert len(findings) == 1
    assert findings[0]["turn"] == 1
    assert findings[0]["affected_count"] == 5
    assert findings[0]["involved_amount"] == 1250.0
    assert findings[0]["key_entities"] == ["省第一人民医院"]

    # 验证轮末状态重置字段
    assert patch["current_turn_query"] is None
    assert patch["turn_type"] is None
    assert patch["retry_count"] == 0
    assert patch["raw_data"] == ""
    assert patch["sql_query"] == ""
    assert patch["sql_validated"] is False
    assert patch["metadata"]["synthesis_done"] is False
