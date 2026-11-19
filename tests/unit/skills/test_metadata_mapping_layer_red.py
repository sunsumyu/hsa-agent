"""
tests/unit/skills/test_metadata_mapping_layer_red.py
====================================================
针对 MetadataMappingLayer 统一归位与避坑指南提取的契约测试：
1. 正常关键词命中生成避坑指南
2. 斜杠复合词 (如 '门诊/特慢病') 拆分多候选匹配能力
3. 未命中任何关键词返回空字符串
4. 知识库配置文件损坏/缺失时的安全降级回退
5. 向后兼容性：同时支持从 app.core.memory.types.semantic 与 app.skills.semantic_layer 导入
"""

import json
import pytest
from app.core.memory.types.semantic import MetadataMappingLayer
from app.skills.semantic_layer import MetadataMappingLayer as LegacyMetadataMappingLayer


def test_import_compatibility():
    """验证两者为同一实现或兼容导出"""
    assert MetadataMappingLayer is LegacyMetadataMappingLayer


def test_detect_direct_keyword(tmp_path):
    kb_file = tmp_path / "mock_kb.json"
    kb_data = {
        "ontology": {
            "职工医保": {
                "physical": "insutype='310'",
                "caveats": "注意区分统筹基金与个人账户"
            }
        }
    }
    kb_file.write_text(json.dumps(kb_data, ensure_ascii=False), encoding="utf-8")

    mapper = MetadataMappingLayer(kb_path=str(kb_file))
    guide = mapper.detect("请排查2024年职工医保的结算明细")

    assert "### 💡 职工医保 业务避坑指南" in guide
    assert "insutype='310'" in guide
    assert "统筹基金与个人账户" in guide


def test_detect_slash_subterm_matching(tmp_path):
    kb_file = tmp_path / "mock_kb.json"
    kb_data = {
        "ontology": {
            "慢病/特慢病/门慢": {
                "physical": "med_type='11' AND chronic_flag='1'",
                "caveats": "特慢病开药周期通常放宽至 30 天，不可直接按常规超量开药判定"
            }
        }
    }
    kb_file.write_text(json.dumps(kb_data, ensure_ascii=False), encoding="utf-8")

    mapper = MetadataMappingLayer(kb_path=str(kb_file))

    # 用其中一个子词触发
    guide = mapper.detect("核查门慢患者的购药情况")
    assert "### 💡 慢病/特慢病/门慢 业务避坑指南" in guide
    assert "chronic_flag='1'" in guide


def test_detect_no_match():
    mapper = MetadataMappingLayer(kb_path="nonexistent_kb.json")
    guide = mapper.detect("今天天气不错，没有任何医保业务术语")
    assert guide == ""


def test_fallback_on_corrupted_kb(tmp_path):
    bad_file = tmp_path / "corrupted.json"
    bad_file.write_text("{ this is not valid json", encoding="utf-8")

    mapper = MetadataMappingLayer(kb_path=str(bad_file))
    # 遇到损坏文件应回退到安全默认项，而不是崩溃抛出 JSONDecodeError
    guide = mapper.detect("职工医保")
    assert "职工医保" in guide
