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

    def test_refund_anomaly_scenario_qa03(self):
        """QA-03: 异常退费与冲正流水应精准路由至 fqz_fymx_test"""
        selector = SceneTableSelector()
        query = "请核查医保结算明细中的异常退费与冲正流水，帮我统计退费总笔数、退费累计金额"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_fymx_test"

    def test_designated_institutions_scenario_qa07(self):
        """QA-07: 全市纳管定点医疗机构与药店应路由至 fqz_all_yy_yd"""
        selector = SceneTableSelector()
        query = "全市目前一共纳管了多少家医保定点医疗机构和定点零售药店？其中二级医院有多少家？"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_all_yy_yd"

    def test_administrative_divisions_scenario_qa08(self):
        """QA-08: 行政区划字典层级划分应路由至 fqz_admdvs"""
        selector = SceneTableSelector()
        query = "我想了解医保行政区划字典的层级划分，系统里国家级、省级、地市级和区县级各有多少个行政区划？"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_admdvs"

    def test_drug_catalog_scenario_qa09(self):
        """QA-09: 临床药品目录库抗生素核查应路由至 fqz_drug_mcs_info_list"""
        selector = SceneTableSelector()
        query = "查一下医保药品目录库，总共收载了多少种临床药品？其中重点管控的头孢类和哌拉西林类各有多少个品种？"
        primary, tables = selector.select_tables(query)
        assert primary == "fqz_drug_mcs_info_list"

    def test_enforcement_hint_synthesizes_missing_companion_archetype(self):
        """[Matt Pocock Deep Module] 伴随缺失场景应同时生成物理表指引与领域原型结构守卫"""
        selector = SceneTableSelector()
        query = "核查未做手术收取麻醉费用的违规就诊明细"
        hint = selector.get_enforcement_hint(query)
        assert hint is not None
        assert "fqz_fymx_test" in hint
        assert "伴随依赖缺失核查" in hint
        assert "子查询 (`NOT IN / NOT EXISTS`)" in hint

    def test_enforcement_hint_synthesizes_split_billing_archetype(self):
        """[Matt Pocock Deep Module] 手术分解场景应注入自连接与跨行聚合守卫"""
        selector = SceneTableSelector()
        query = "核查主手术与子步骤分解收费违规行为"
        hint = selector.get_enforcement_hint(query)
        assert hint is not None
        assert "手术分解与套收计费核查" in hint
        assert "自连接 JOIN 或分组计数" in hint

    def test_enforcement_hint_synthesizes_drug_resale_archetype(self):
        """[Matt Pocock Deep Module] 药贩子套现场景应注入参保人聚合与禁LIMIT采样守卫"""
        selector = SceneTableSelector()
        query = "核查药贩子高频跨机构倒药套现网络"
        hint = selector.get_enforcement_hint(query)
        assert hint is not None
        assert "药贩子套现与频繁异常购药网络" in hint
        assert "GROUP BY psn_no" in hint

    def test_enforcement_hint_synthesizes_reconciliation_archetype(self):
        """[Matt Pocock Deep Module] 资金对账任务应注入宏观对账禁LIMIT采样守卫"""
        selector = SceneTableSelector()
        query = "请对2024年1月的医保基金结算数据进行日结对账，检查资金是否存在差异"
        hint = selector.get_enforcement_hint(query)
        assert hint is not None
        assert "资金对账与宏观汇总" in hint
        assert "全量聚合统计" in hint


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
        """场景映射应从配置文件加载且包含五大核心表"""
        selector = SceneTableSelector()
        # 检查映射是否已加载 5 张核心表
        assert len(selector._mapping) >= 5
        assert "fqz_fymx_test" in selector._mapping
        assert "fqz_gz_jzsj_all_ql" in selector._mapping
        assert "fqz_all_yy_yd" in selector._mapping
        assert "fqz_admdvs" in selector._mapping
        assert "fqz_drug_mcs_info_list" in selector._mapping


if __name__ == "__main__":
    pytest.main([__file__, "-v"])