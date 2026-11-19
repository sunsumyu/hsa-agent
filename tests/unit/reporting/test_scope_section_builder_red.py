"""
tests/unit/reporting/test_scope_section_builder_red.py
======================================================
[SPEC-227 / Matt Pocock Deep Module] 报告核查口径与技术实现生成深模块测试 (红灯先行)
"""

import pytest
from app.reporting.scope_section_builder import build_scope_section


def test_build_scope_section_restricted():
    """测试受限核查模式下生成防御性口径说明"""
    scope_text = build_scope_section(
        sql="SELECT * FROM fqz_fymx_test",
        table_info="fqz_fymx_test",
        trace=[],
        is_restricted=True,
    )
    assert "受限核查" in scope_text
    assert "未物理执行 SQL 查询" in scope_text


def test_build_scope_section_with_semantic_alignment():
    """测试具有白盒语义靶向映射时的结构化排版"""
    semantic_align = {
        "rewritten_question": "排查男性妇科结算",
        "disease_keywords": ["子宫内膜炎"],
        "aligned_codes": ["N71.0"],
        "hospital_levels": ["三级乙等"],
        "temp_table": "tmp_hosp_level",
    }
    scope_text = build_scope_section(
        sql="SELECT * FROM fqz_fymx_test WHERE gend = '1'",
        table_info="fqz_fymx_test",
        trace=["PLAN: 规划完成", "SQL: 执行对碰", "VALIDATE: 通过"],
        methodology="基于限定性别的排他核查",
        semantic_alignment=semantic_align,
    )
    assert "## 二、核查口径与技术实现" in scope_text
    assert "语义靶向映射 (Semantic Anchor Mapping)" in scope_text
    assert "子宫内膜炎" in scope_text
    assert "N71.0" in scope_text
    assert "tmp_hosp_level" in scope_text
    assert "基于限定性别的排他核查" in scope_text


def test_build_scope_section_synthetic_probe_fallback():
    """测试在缺失显式 SQL 时，根据问题特征智能合成高仿真 SQL 探针"""
    # 模拟拔牙场景
    scope_dental = build_scope_section(
        sql=None,
        table_info=None,
        trace=[],
        user_question="排查同一颗牙齿重复拔牙骗保行为",
    )
    assert "拔牙" in scope_dental or "K02" in scope_dental

    # 模拟手术连轴转场景
    scope_surgery = build_scope_section(
        sql=None,
        table_info=None,
        trace=[],
        user_question="审查主刀医师单日手术时长是否超过物理极限",
    )
    assert "手术" in scope_surgery or "麻醉" in scope_surgery
