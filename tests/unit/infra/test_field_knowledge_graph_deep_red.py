import pytest
from app.infra.medical_intent_lexicon import expand_medical_intent, MEDICAL_KNOWLEDGE_MAP
from app.infra.field_alias_catalog import FieldAliasCatalog
from app.infra.sql_field_sanitizer import SQLFieldSanitizer
from app.infra.field_knowledge_graph import FieldKnowledgeGraph, field_kg


def test_medical_intent_lexicon():
    """测试医学意图扩展词典深模块"""
    assert "妇科" in MEDICAL_KNOWLEDGE_MAP
    expansions = expand_medical_intent("排查妇科违规用药")
    assert any("妇科" in item or "子宫" in item or "阴道" in item for item in expansions)
    assert expand_medical_intent("今天天气不错") == []


def test_field_alias_catalog():
    """测试字段别名编目深模块解析"""
    catalog = FieldAliasCatalog()
    # 别名解析为正规字段
    assert catalog.resolve("hosp_id") == "fixmedins_code"
    assert catalog.resolve("医疗机构编码") == "fixmedins_code"
    assert catalog.resolve("total_fee") == "medfee_sumamt"
    # 禁用词识别
    assert catalog.is_forbidden("hosp_code") is True
    assert catalog.is_forbidden("fixmedins_code") is False


def test_sql_field_sanitizer_protects_aliases():
    """测试 SQL 字段自动纠错深模块与 AS 别名保护"""
    sanitizer = SQLFieldSanitizer(catalog=FieldAliasCatalog())

    # 1. 替换非法的 hosp_code 与 total_fee
    sql = "SELECT hosp_code, total_fee FROM fqz_gz_jzsj_all_ql"
    clean_sql, warnings = sanitizer.sanitize_sql(sql)
    assert "fixmedins_code" in clean_sql
    assert "medfee_sumamt" in clean_sql
    assert "hosp_code" not in clean_sql

    # 2. 严格保护 AS 后面命名的别名，避免破坏外层语义
    as_sql = "SELECT medfee_sumamt AS total_fee, sum(fund_pay_sumamt) AS total_amount FROM t GROUP BY total_fee"
    clean_as_sql, _ = sanitizer.sanitize_sql(as_sql)
    assert "AS total_fee" in clean_as_sql
    assert "AS total_amount" in clean_as_sql


def test_field_knowledge_graph_facade():
    """测试 FieldKnowledgeGraph 门面整合契约"""
    assert field_kg.resolve("hosp_name") == "fixmedins_name"
    assert field_kg.is_forbidden("hosp_code") is True
    prompt_snippet = field_kg.format_for_prompt(max_fields=3)
    assert "[字段知识图谱]" in prompt_snippet
    assert "fixmedins_code" in prompt_snippet
