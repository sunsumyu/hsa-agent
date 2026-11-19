"""
tests/unit/schema/test_scene_match_evaluator_deep_red.py
========================================================
[Matt Pocock Deep Module Red Test] 场景匹配打分策略与关联图谱链接解耦架构审计
"""

import pytest
from app.core.schema.scene_match_evaluator import SceneMatchEvaluator
from app.core.schema.table_relation_linker import TableRelationLinker


def test_scene_match_evaluator_specificity_entropy_weighting():
    """验证场景匹配算子的长词特异性信息熵加权逻辑"""
    evaluator = SceneMatchEvaluator()

    mapping = {
        "table_short": ["纳管", "费用"],
        "table_specific": ["定点医药机构宏观月度费用统计报表", "全库纳管"]
    }

    # 查询包含专有长报表全称
    query = "请调取定点医药机构宏观月度费用统计报表进行核验"
    scores = evaluator.evaluate(query, mapping)

    # table_specific 的长词应当产生明显高于 table_short 的高分
    assert "table_specific" in scores
    assert scores["table_specific"] > scores.get("table_short", 0)
    assert scores["table_specific"] >= len("定点医药机构宏观月度费用统计报表")


def test_scene_match_evaluator_explicit_table_name_boost():
    """验证显式提及物理表名时获得绝对主导提权 (+50 分)"""
    evaluator = SceneMatchEvaluator()

    mapping = {
        "fqz_fymx_test": ["门诊明细", "刷单"],
        "fqz_gz_jzsj_all_ql": ["住院", "结算"]
    }

    # 即使包含门诊明细等关键词，若显式要求查询 fqz_gz_jzsj_all_ql，主导权应归属该表
    query = "在 fqz_gz_jzsj_all_ql 中统计门诊明细数据"
    scores = evaluator.evaluate(query, mapping)

    assert "fqz_gz_jzsj_all_ql" in scores
    assert scores["fqz_gz_jzsj_all_ql"] >= 50
    assert scores["fqz_gz_jzsj_all_ql"] > scores.get("fqz_fymx_test", 0)


def test_table_relation_linker_auto_pull():
    """验证表间关联图谱按查询关键词自动拉入关联字典表"""
    linker = TableRelationLinker()

    relation_graph = {
        "fqz_gz_jzsj_all_ql": {
            "auto_pull": [
                {
                    "table": "fqz_all_yy_yd",
                    "pull_keywords": ["定点医疗机构", "药店名录", "医院"],
                    "hint": "包含机构字典"
                },
                {
                    "table": "fqz_admdvs",
                    "pull_keywords": ["行政区划", "区划字典"],
                    "hint": "包含区划字典"
                }
            ]
        }
    }

    # 查询包含医院关键词
    related = linker.resolve_related_tables(
        primary_table="fqz_gz_jzsj_all_ql",
        user_query="排查某定点医疗机构的就诊记录",
        relation_graph=relation_graph
    )

    pulled_tables = [t for t, _ in related]
    assert "fqz_all_yy_yd" in pulled_tables
    assert "fqz_admdvs" not in pulled_tables  # 未触发区划关键词
