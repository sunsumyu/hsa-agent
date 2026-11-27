"""
tests/unit/infra/test_field_knowledge_graph_red.py
==================================================
Matt Pocock 契约测试：字段知识图谱与语义意图扩展深模块
验证从 neo4j_manager 解耦出来的 FieldKnowledgeGraph 和 expand_medical_intent。
"""

import pytest
from app.infra.field_knowledge_graph import (
    FieldKnowledgeGraph,
    expand_medical_intent,
    MEDICAL_KNOWLEDGE_MAP,
    FIELD_ALIAS_REGISTRY,
)


class TestFieldKnowledgeGraphDeepModule:
    @pytest.fixture
    def fkg(self):
        return FieldKnowledgeGraph()

    def test_expand_medical_intent(self):
        # 妇科意图扩展
        expansions = expand_medical_intent("排查妇科结算项目")
        assert "阴道镜检查" in expansions or "妇科门诊" in expansions

        # 分解住院意图扩展
        expansions_drg = expand_medical_intent("检查是否存在分解住院嫌疑")
        assert "24小时再次入院" in expansions_drg or "多单结算" in expansions_drg

        # 无关文本无扩展
        assert expand_medical_intent("常规通用查询") == []

    def test_resolve_canonical_field(self, fkg):
        # 别名解析为正规名
        assert fkg.resolve("医疗机构编码") == "fixmedins_code"
        assert fkg.resolve("机构代码") == "fixmedins_code"
        assert fkg.resolve("total_fee") == "medfee_sumamt"
        assert fkg.resolve("settle_time") == "setl_time"

        # 原正规名保持原样
        assert fkg.resolve("fixmedins_code") == "fixmedins_code"
        assert fkg.resolve("psn_no") == "psn_no"

        # 未知字段返回 None
        assert fkg.resolve("unknown_random_col_xyz") is None

    def test_is_forbidden_aliases(self, fkg):
        # 常见高危幻觉或错误字段
        assert fkg.is_forbidden("hosp_code") is True
        assert fkg.is_forbidden("total_fee") is True
        assert fkg.is_forbidden("gender") is True
        assert fkg.is_forbidden("vix") is True  # 虚拟计算指标
        assert fkg.is_forbidden("los") is True

        # 合法正规字段不被标记为 forbidden
        assert fkg.is_forbidden("fixmedins_code") is False
        assert fkg.is_forbidden("psn_no") is False

    def test_sanitize_sql_and_protect_alias(self, fkg):
        # 1. 禁用字段自动纠错
        raw_sql = "SELECT hosp_code, total_fee FROM fqz_gz_jzsj_all_ql"
        cleaned_sql, warnings = fkg.sanitize_sql(raw_sql)
        assert "fixmedins_code" in cleaned_sql
        assert "medfee_sumamt" in cleaned_sql
        assert len(warnings) >= 2

        # 2. 严格保护 AS 显式定义的别名
        raw_sql_with_alias = (
            "SELECT medfee_sumamt AS total_amount "
            "FROM fqz_gz_jzsj_all_ql "
            "ORDER BY total_amount DESC"
        )
        cleaned_alias_sql, _ = fkg.sanitize_sql(raw_sql_with_alias)
        # 不应将 "AS total_amount" 或 ORDER BY 后的别名强行替换
        assert "AS total_amount" in cleaned_alias_sql
        assert "ORDER BY total_amount" in cleaned_alias_sql

    def test_format_for_prompt_and_canonical_fields(self, fkg):
        prompt_snippet = fkg.format_for_prompt(max_fields=5)
        assert "**[字段知识图谱]" in prompt_snippet
        assert "fixmedins_code" in prompt_snippet

        fields = fkg.get_canonical_fields(table="fqz_gz_jzsj_all_ql")
        assert len(fields) > 5
        canonicals = [f["canonical"] for f in fields]
        assert "fixmedins_code" in canonicals
        assert "fund_pay_sumamt" in canonicals
