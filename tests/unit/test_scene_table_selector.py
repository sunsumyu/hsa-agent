"""
tests/unit/test_scene_table_selector.py
========================================
[V1.0] 场景表选择器单元测试

测试 SceneTableSelector 的场景匹配和强制提示生成逻辑
"""

import pytest
from app.core.scene_table_selector import SceneTableSelector, scene_table_selector


class TestSceneTableSelector:
    """场景表选择器测试"""

    def test_qa_cust26_scenario(self):
        """QA-CUST-26 场景应选择 fqz_fymx_test"""
        selector = SceneTableSelector()
        query = "核查乡镇卫生院门诊统筹批量刷单行为"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_fymx_test"
        assert "fqz_fymx_test" in tables

    def test_village_health_station_scenario(self):
        """村卫生室场景应选择 fqz_fymx_test"""
        selector = SceneTableSelector()
        query = "分析村卫生室连续刷卡违规模式"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_fymx_test"

    def test_dental_scenario(self):
        """拔牙/口腔场景应选择 fqz_fymx_test"""
        selector = SceneTableSelector()
        query = "核查拔牙项目收费异常"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_fymx_test"

    def test_hospitalization_scenario(self):
        """住院场景应选择 fqz_gz_jzsj_all_ql"""
        selector = SceneTableSelector()
        query = "核查分解住院违规行为"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_gz_jzsj_all_ql"

    def test_pharmacy_scenario(self):
        """药店购药场景应选择 fqz_gz_jzsj_all_ql"""
        selector = SceneTableSelector()
        query = "分析定点药店购药高频刷卡"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_gz_jzsj_all_ql"

    def test_overlap_hospitalization_scenario(self):
        """重叠住院场景应选择 fqz_gz_jzsj_all_ql"""
        selector = SceneTableSelector()
        query = "核查重叠住院压床违规"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_gz_jzsj_all_ql"

    def test_no_match_returns_main_table(self):
        """无场景匹配时返回默认主表"""
        selector = SceneTableSelector()
        query = "查询医疗机构基本信息"
        primary, tables = selector.select_tables(query)
        # 默认返回 fqz_gz_jzsj_all_ql（主表）
        assert primary == "fqz_gz_jzsj_all_ql"

    def test_enforcement_hint_for_fymx(self):
        """门诊场景应生成强制提示"""
        selector = SceneTableSelector()
        query = "QA-CUST-26 乡镇卫生院连续刷卡"
        hint = selector.get_enforcement_hint(query)
        assert hint is not None
        assert "fqz_fymx_test" in hint
        assert "严禁" in hint
        assert "toDateTime(substring(trim(setl_time),1,19))" in hint

    def test_no_enforcement_hint_for_main_table(self):
        """住院场景不应生成强制提示（使用默认主表）"""
        selector = SceneTableSelector()
        query = "核查住院天数异常"
        hint = selector.get_enforcement_hint(query)
        # 住院场景使用默认主表，不需要强制提示
        assert hint is None

    def test_multiple_keywords_higher_score(self):
        """多关键词匹配应得到更高分数"""
        selector = SceneTableSelector()
        # 包含多个门诊关键词的查询
        query = "乡镇卫生院村卫生室门诊统筹批量刷单连续刷卡"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_fymx_test"

    def test_mixed_scenario_priority(self):
        """混合场景关键词的优先级测试"""
        selector = SceneTableSelector()
        # 包含门诊和住院关键词的查询，门诊关键词更多应优先
        query = "乡镇卫生院门诊统筹住院分解住院"
        primary, tables = selector.select_tables(query)
        # 门诊关键词（乡镇卫生院, 门诊统筹）= 2
        # 住院关键词（住院, 分解住院）= 2
        # 得分相同时应返回第一个匹配的表
        assert primary in ["fqz_fymx_test", "fqz_gz_jzsj_all_ql"]

    def test_singleton_instance(self):
        """测试单例实例"""
        # 确保模块级单例可用
        assert scene_table_selector is not None
        primary, tables = scene_table_selector.select_tables("乡镇卫生院刷单")
        assert primary == "fqz_fymx_test"


class TestSceneTableSelectorIntegration:
    """集成测试 - 与 SchemaRegistry 集成"""

    def test_selected_table_exists_in_registry(self):
        """选择的表应在 SchemaRegistry 中存在"""
        from app.core.registry.schema_registry import schema_registry

        selector = SceneTableSelector()

        for query in [
            "乡镇卫生院刷单",
            "住院天数异常",
            "村卫生室门诊统筹"
        ]:
            primary, _ = selector.select_tables(query)
            entry = schema_registry.get_table(primary)
            assert entry is not None, f"表 {primary} 不在 SchemaRegistry 中"

    def test_scene_table_mapping_loaded(self):
        """场景映射应从配置文件加载"""
        selector = SceneTableSelector()
        # 检查映射是否已加载
        assert len(selector._mapping) >= 2
        assert "fqz_fymx_test" in selector._mapping
        assert "fqz_gz_jzsj_all_ql" in selector._mapping


if __name__ == "__main__":
    pytest.main([__file__, "-v"])