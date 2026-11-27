"""
tests/unit/skills/test_schema_pruner_and_governance_red.py
==========================================================
[Matt Pocock Deep Module Red Test] 字段相关性剪枝器与审计安全治理指南解耦测试
"""

import pytest
from unittest.mock import MagicMock
from app.skills.schema.schema_field_pruner import (
    SchemaFieldPruner,
    schema_field_pruner,
)
from app.skills.rules.audit_governance_guide import (
    AuditGovernanceGuide,
    audit_governance_guide,
)


def test_schema_field_pruner_no_pruning_under_limit():
    """字段数未超过 max_fields 时不作截断"""
    pruner = SchemaFieldPruner()
    raw_fields = [
        {"field": "psn_no", "desc": "人员编号"},
        {"field": "setl_id", "desc": "结算ID"},
    ]
    res = pruner.prune_fields(raw_fields, user_question="查询费用", max_fields=35)
    assert len(res) == 2
    assert res == raw_fields


def test_schema_field_pruner_prioritization_and_scoring():
    """验证超过上限时，按照：问题命中(100) > 核心字段(90) > 描述词(50) > 其他(0) 进行剪枝"""
    pruner = SchemaFieldPruner()
    # 构造 40 个字段
    raw_fields = []
    # 1 个命中问题的自定义字段
    raw_fields.append({"field": "special_herb_code", "desc": "特殊中草药编码"})
    # 1 个核心业务字段
    raw_fields.append({"field": "psn_no", "desc": "人员编号"})
    # 1 个描述命中问题的字段
    raw_fields.append({"field": "item_code", "desc": "包含中草药标识的项目编码"})
    # 其余填充 37 个无关字段
    for i in range(37):
        raw_fields.append({"field": f"dummy_col_{i}", "desc": f"无关字段_{i}"})

    assert len(raw_fields) == 40

    pruned = pruner.prune_fields(
        raw_fields,
        user_question="中草药 special_herb_code 结算",
        max_fields=3,
    )

    assert len(pruned) == 3
    # 应该精准挑选出得分最高的前 3 个
    pruned_field_names = [f["field"] for f in pruned]
    assert "special_herb_code" in pruned_field_names  # 100分
    assert "psn_no" in pruned_field_names            # 90分
    assert "item_code" in pruned_field_names         # 50分


def test_audit_governance_guide_rendering():
    """验证安全治理守则生成完整包含治理禁区、红线与图谱提示"""
    guide = AuditGovernanceGuide()

    mock_registry = MagicMock()
    mock_registry.get_forbidden_table_names.return_value = ["fake_t1", "fake_t2"]
    mock_registry.get_valid_prefixes.return_value = ["fqz_"]
    mock_registry.get_sensitive_fields.return_value = ["idcard", "tel"]

    mock_neo4j = MagicMock()
    mock_neo4j.get_audit_graph_hints.return_value = "\n## 🕸️ 图谱查询指引: 使用 Cypher 查欺诈团伙\n"

    rendered = guide.build_governance_guidance(
        schema_registry_inst=mock_registry,
        neo4j_manager_inst=mock_neo4j,
    )

    assert "🚨 [审计治理与安全禁区 - 强制合规提示]" in rendered
    assert "`fake_t1`" in rendered
    assert "主子表分离原则" in rendered
    assert "🛑 [企业级审计红线]" in rendered
    assert "图谱查询指引" in rendered
