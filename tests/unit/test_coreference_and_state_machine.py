# -*- coding: utf-8 -*-
"""
tests/unit/test_coreference_and_state_machine.py
================================================
验证 SPEC-227 多轮会话状态机解耦、指代消解与审计底稿装配器核心接缝行为
"""

import pytest
from app.core.context.coreference_rewriter import coreference_rewriter
from app.reporting.report_synthesizer import report_synthesizer


def test_turn_type_classification():
    """测试多轮任务意图分类准确性"""
    # 1. SYNTHESIS 意图
    q_synthesis = "请综合前面所有9轮的核查发现、涉及机构、重点药品、违规金额与合规扫描结论，出具一份完整的阶段性审计工作底稿报告。"
    assert coreference_rewriter.classify_turn_type(q_synthesis) == coreference_rewriter.TASK_SYNTHESIS

    # 2. RECALL 意图
    q_recall = "回顾前序核查：我们在第 3 轮便签中重点标记的嫌疑机构名称叫什么？"
    assert coreference_rewriter.classify_turn_type(q_recall) == coreference_rewriter.TASK_RECALL

    # 3. NOTE 意图
    q_note = "请将排名第一的医疗机构作为重点涉案嫌疑对象，记录到本次审计的便签簿中，便于后续穿透追踪。"
    assert coreference_rewriter.classify_turn_type(q_note) == coreference_rewriter.TASK_NOTE

    # 4. CONSOLIDATE 意图
    q_cons = "请将本次『男性结算女性专属用药』的违规特征与判定逻辑总结为标准审计经验规则，沉淀至长期经验库。"
    assert coreference_rewriter.classify_turn_type(q_cons) == coreference_rewriter.TASK_CONSOLIDATE

    # 5. 常规 QUERY 意图
    q_query1 = "请重点排查2024年就诊费用明细中是否存在参保人登记为男性，却结算了妇科专属用药？"
    assert coreference_rewriter.classify_turn_type(q_query1) == coreference_rewriter.TASK_QUERY

    q_query2 = "在上述违规记录中，按定点医药机构统计，涉案金额最高的前三家医疗机构分别叫什么？"
    assert coreference_rewriter.classify_turn_type(q_query2) == coreference_rewriter.TASK_QUERY


def test_coreference_resolution_expansion():
    """测试代词指代消解展开"""
    mock_state = {
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "请重点排查2024年就诊费用明细中是否存在参保人登记为男性，却结算了妇科专属用药（益母草颗粒、地屈孕酮片）的情况？",
                "resolved_query": "在2024年就诊费用明细中参保人登记为男性结算妇科专属用药（益母草颗粒、地屈孕酮片）",
                "key_entities": ["XX市第一人民医院", "益母草颗粒"],
                "affected_count": 28,
                "involved_amount": 5420.5
            }
        ],
        "audit_notes": [
            "【重点线索】涉案金额第一的医院（XX市第一人民医院）存在异常集中开具男性妇科专属药品行为，纳入重点监控名单。"
        ]
    }

    # 测试第 2 轮代词展开
    q_turn2 = "在上述违规记录中，按定点医药机构统计，涉案金额最高的前三家医疗机构分别叫什么？列出各家涉案金额。"
    resolved2, ttype2, _ = coreference_rewriter.resolve_coreference(q_turn2, mock_state)
    assert ttype2 == coreference_rewriter.TASK_QUERY
    assert "在2024年就诊费用明细中参保人登记为男性结算妇科专属用药" in resolved2
    assert "按定点医药机构统计" in resolved2

    # 测试第 4 轮代词展开绑定嫌疑医院
    q_turn4 = "针对刚刚记入便签的重点嫌疑医院，查询其结算妇科专属药品金额最高的前三位参保人姓名与金额。"
    resolved4, ttype4, entities4 = coreference_rewriter.resolve_coreference(q_turn4, mock_state)
    assert ttype4 == coreference_rewriter.TASK_QUERY
    assert "重点嫌疑机构『XX市第一人民医院』" in resolved4
    assert "XX市第一人民医院" in entities4


def test_report_synthesizer_workpaper():
    """测试阶段性审计工作底稿装配器"""
    mock_state = {
        "session_id": "TEST-SESSION-999",
        "accumulated_findings": [
            {
                "turn": 1,
                "user_query": "排查男性结算妇科专属用药",
                "target_tables": ["fqz_fymx_test"],
                "key_entities": ["益母草颗粒"],
                "affected_count": 50,
                "involved_amount": 12800.0,
                "summary_conclusion": "确认男性使用妇科专属药品违规"
            },
            {
                "turn": 2,
                "user_query": "统计涉案金额前三家机构",
                "target_tables": ["fqz_fymx_test"],
                "key_entities": ["XX市第一人民医院"],
                "affected_count": 3,
                "involved_amount": 9600.0,
                "summary_conclusion": "XX市第一人民医院金额位列第一"
            },
            {
                "turn": 6,
                "user_query": "结算主表中基金支付大于医疗总费用",
                "target_tables": ["fqz_gz_jzsj_all_ql"],
                "key_entities": [],
                "affected_count": 0,
                "involved_amount": 0.0,
                "summary_conclusion": "全量扫描未发现违规单据，指标合规"
            }
        ],
        "audit_notes": [
            "【重点线索】涉案金额第一的医院（XX市第一人民医院）存在异常集中开具男性妇科专属药品行为，纳入重点监控名单。"
        ]
    }

    workpaper = report_synthesizer.synthesize_workpaper(mock_state)

    # 断言公文规范与关键要素
    assert "医疗保障基金智能监督检查阶段性审计工作底稿" in workpaper
    assert "TEST-SESSION-999" in workpaper
    assert "3 轮" in workpaper
    assert "22,400.00" in workpaper
    assert "XX市第一人民医院" in workpaper
    assert "fqz_gz_jzsj_all_ql" in workpaper
    assert "免责排查结论" in workpaper
    assert "审计处理意见与后续调查建议" in workpaper
