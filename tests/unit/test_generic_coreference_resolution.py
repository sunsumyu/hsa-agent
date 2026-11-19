# -*- coding: utf-8 -*-
"""
tests/unit/test_generic_coreference_resolution.py
=================================================
验证彻底消除硬编码后的通用指代消解器：
测试儿童使用成人药、重复住院、高额耗材、血液透析等多种完全不同的业务场景，
确保无论用户问什么业务，系统都能动态完成从句提取与代词展开，严禁场景过拟合。
"""

import pytest
from app.core.context.coreference_rewriter import coreference_rewriter


def test_generic_coreference_child_pediatric_scenario():
    """场景 1：儿童使用成人专用药品核查"""
    mock_state = {
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "请排查2024年就诊明细中14岁以下儿童开具成人专用退热药尼美舒利颗粒的情况？",
                "resolved_query": "在2024年就诊费用明细中参保人年龄小于14岁结算成人专用退热药尼美舒利颗粒",
                "key_entities": ["儿童专科医院", "尼美舒利颗粒"],
                "affected_count": 42,
                "involved_amount": 1890.0,
            }
        ]
    }

    user_query = "在上述违规记录中，按开方科室汇总，排名前三的科室是哪些？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_query, mock_state)

    assert turn_type == coreference_rewriter.TASK_QUERY
    # 验证动态继承了年龄小于14岁与尼美舒利的约束，而不是被男性妇科药覆盖
    assert "年龄小于14岁" in resolved
    assert "尼美舒利颗粒" in resolved
    assert "按开方科室汇总" in resolved
    # 严禁残留旧硬编码
    assert "益母草" not in resolved
    assert "男性" not in resolved


def test_generic_coreference_temporal_overlap_scenario():
    """场景 2：同日多次挂号与异地就医时序重叠"""
    mock_state = {
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "帮我查一下2024年同一天在不同异地定点医院办理住院结算的异常流水",
                "resolved_query": "2024年同一参保人在同一结算日跨两家异地定点医院住院结算",
                "key_entities": ["异地住院异常流水"],
                "affected_count": 15,
                "involved_amount": 98000.0,
            }
        ]
    }

    user_query = "其中涉及总统筹基金支付金额最高的三位参保人分别是谁？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_query, mock_state)

    assert turn_type == coreference_rewriter.TASK_QUERY
    # 验证动态提取了异地住院的上下文
    assert "跨两家异地定点医院住院结算" in resolved
    assert "涉及总统筹基金支付金额最高的三位参保人" in resolved


def test_generic_coreference_hemodialysis_frequency_scenario():
    """场景 3：血液透析超频次违规排查"""
    mock_state = {
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "请重点核查门诊慢特病血液透析项目月度结算超过15次的高频患者名单？",
                "resolved_query": "在门诊慢特病结算中血液透析项目单月结算频次大于15次",
                "key_entities": ["血液透析", "市中医院"],
            }
        ]
    }

    user_query = "上述违规记录中，涉及基金支付总金额是多少？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_query, mock_state)

    assert turn_type == coreference_rewriter.TASK_QUERY
    assert "血液透析" in resolved
    assert "单月结算频次大于15次" in resolved
    assert "涉及基金支付总金额是多少" in resolved


def test_generic_oral_correction_without_character_truncation():
    """场景 4：口语反悔纠偏（验证无论多长的历史任务命题均不发生截断断句）"""
    long_task = "在2024年全省各级定点医药机构门诊与住院结算流水中排查涉及高额医用耗材人工关节植入物多收重收套收的违规明细清单"
    mock_state = {
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "查人工关节套收",
                "resolved_query": long_task,
            }
        ]
    }

    user_turn2 = "不对，先别查全省了，把范围缩小到市级三甲公立医院重新查！"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_turn2, mock_state)

    assert turn_type == coreference_rewriter.TASK_QUERY
    assert "推翻旧条件并按最新口径重新执行" in resolved
    # 验证完整包含长任务文本，没有在40字符处被强行截断
    assert "多收重收套收的违规明细清单" in resolved
    assert "市级三甲公立医院" in resolved
