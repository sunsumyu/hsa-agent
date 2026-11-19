"""
tests/unit/reporting/test_visualization_templates_deep_red.py
============================================================
Matt Pocock 风格深模块红灯测试：
验证 app/reporting/visualization_templates.py 的 AuditVisualizationRegistry
及其 13 个反欺诈可视化专题的准确性、策略注册能力与向后兼容性。
"""

import pytest
from app.reporting.visualization_templates import (
    render_audit_visualization,
    visualization_registry,
    AuditVisualizationRegistry,
    VisualizationTopic,
    _viz_family_fraud_positive,
    _viz_family_fraud_zero,
    _viz_surgeon_overlap,
    _viz_surgeon_workload,
    _viz_therapy_overlap,
    _viz_therapy_normal,
    _viz_batch_billing_positive,
    _viz_batch_billing_zero,
    _viz_pharmacy_inventory,
    _viz_duplicate_testing,
    _viz_transfer_loop,
    _viz_consumables_match,
    _viz_dental_chart,
    _viz_icu_bundled,
    _viz_medication_hoarding,
    _viz_medication_hoarding_zero,
    _viz_high_value_ranking_positive,
    _viz_high_value_ranking_zero,
    _viz_drg_revolving,
)


class TestVisualizationTemplatesDeepModule:
    """全面覆盖 13 个反欺诈可视化专题的契约测试"""

    def test_topic_1_family_fraud(self):
        # 命中 > 0
        pos = render_audit_visualization("请画出家族套保团伙的电话和地址关联网络", finding_count=2)
        assert "```mermaid" in pos
        assert "家庭共用特征层" in pos
        assert "Store" in pos

        # 命中 = 0
        zero = render_audit_visualization("家族套保图谱", finding_count=0)
        assert "Theoretical Cluster Topology" in zero
        assert "协同聚类层" in zero

    def test_topic_2_surgeon_conflict_and_workload(self):
        # 分身冲突
        overlap = render_audit_visualization("主刀医师分身术多点重叠冲突", finding_count=1)
        assert "Surgeon Spatiotemporal Overlap Conflict Gantt" in overlap
        assert "物理冲突" in overlap

        # 工作量极限
        workload = render_audit_visualization("主刀医生连轴转手术时间轴资质", finding_count=0)
        assert "Surgeon Surgery Duration Timeline Gantt" in workload
        assert "当日累计有效手术时长" in workload

    def test_topic_3_therapy_overlap(self):
        # 阳性重叠
        pos = render_audit_visualization("康复理疗手法推拿排班", finding_count=3)
        assert "Therapist Spatiotemporal Overlap Gantt" in pos
        assert "时间重叠违规" in pos

        # 阴性合规
        zero = render_audit_visualization("理疗师推拿按摩", finding_count=0)
        assert "Therapist Sequential Schedule Gantt" in zero
        assert "顺序排班图" in zero

    def test_topic_4_batch_billing(self):
        # 阳性秒级刷卡
        pos = render_audit_visualization("门诊连续秒级批量刷卡时序异常", finding_count=5)
        assert "Automated Batch Billing Sequence" in pos
        assert "机器脚本自动流水线批量刷卡" in pos

        # 阴性正常间隔
        zero = render_audit_visualization("快速刷单刷卡", finding_count=0)
        assert "Normal Outpatient Billing Intervals" in zero
        assert "正常就诊间隔" in zero

    def test_topic_5_pharmacy_inventory(self):
        res = render_audit_visualization("定点大药房进销存负库存核查", finding_count=0)
        assert "Pharmacy Inventory Discrepancy Flow" in res
        assert "进销存倒挂" in res

    def test_topic_6_duplicate_testing(self):
        res = render_audit_visualization("跨院重复检查与增强ct核磁共振互认", finding_count=0)
        assert "Cross-Hospital Duplicate Testing sliding window" in res
        assert "卫健委3天互认限制窗口" in res

    def test_topic_7_malicious_transfer(self):
        res = render_audit_visualization("逼近盈亏临界点肿瘤重症恶意转院推诿", finding_count=0)
        assert "DRG Transfer Loop Sequence" in res
        assert "诱导/恶意推诿办理出院" in res

    def test_topic_8_consumables_match(self):
        res = render_audit_visualization("骨科不用工具耗材配对钛板钛钉缺失", finding_count=0)
        assert "Procedure vs Consumables Match Flow" in res
        assert "干活不用工具" in res

    def test_topic_9_dental_chart(self):
        res = render_audit_visualization("口腔拔牙同一牙位重复拔除", finding_count=0)
        assert "FDI Tooth Chart Repetition Analysis" in res
        assert "FDI #36" in res

    def test_topic_10_icu_bundled(self):
        res = render_audit_visualization("ICU双头收费抢救打包重复计费", finding_count=0)
        assert "ICU Charge Inclusions Matrix" in res
        assert "吸痰及气道护理" in res

    def test_topic_11_medication_hoarding(self):
        # 阳性跨院囤药
        pos = render_audit_visualization("跨院重复开药慢病囤药滚动时间窗", finding_count=2)
        assert "跨院重复开药时序追踪图" in pos
        assert "跨院囤药/重复开药违规" in pos

        # 阴性滑动窗口
        zero = render_audit_visualization("跨院慢病囤药开药时间窗", finding_count=0)
        assert "Medication Hoarding sliding window timeline" in zero
        assert "物理时空超额重叠段" in zero

    def test_topic_12_drg_revolving(self):
        res = render_audit_visualization("DRG假出院48小时再次入院分解住院", finding_count=0)
        assert "DRG Revolving Door Sequence" in res
        assert "Ventilator & Oxygen Chamber Continuity Timeline" in res

    def test_topic_13_high_value_ranking(self):
        # 阳性排名
        pos = render_audit_visualization("大额结算金额排名最高频繁异常案件", finding_count=1)
        assert "大额结算排名与频次分布可视化" in pos
        assert "xychart-beta" in pos

        # 阴性三档敏感度
        zero = render_audit_visualization("大额最高结算金额排名", finding_count=0)
        assert "大额结算排名扫描验证模型" in zero
        assert "三档敏感度模拟" in zero

    def test_unrelated_query_returns_empty(self):
        assert render_audit_visualization("普通医保政策常识咨询", finding_count=0) == ""
        assert render_audit_visualization("", finding_count=0) == ""

    def test_registry_deep_module_capabilities(self):
        # 注册表应包含 13 个内建专题
        topics = visualization_registry.get_registered_topics()
        assert len(topics) >= 13
        assert "family_fraud" in topics
        assert "surgeon_timeline" in topics
        assert "drg_revolving" in topics

        # 支持动态注册扩展策略
        custom_topic = VisualizationTopic(
            topic_id="hemodialysis_frequency",
            keywords=["血液透析", "血透", "造瘘"],
            renderer=lambda count, q: f"```mermaid\nhemodialysis_chart_count_{count}\n```"
        )
        registry = AuditVisualizationRegistry()
        registry.register(custom_topic, prepend=True)

        rendered = registry.render("血液透析超频次收费核查", finding_count=5)
        assert "hemodialysis_chart_count_5" in rendered

    def test_backward_compatibility_private_builders(self):
        # 验证所有历史私有构建器依然存在且可直接调用
        assert "```mermaid" in _viz_family_fraud_positive()
        assert "```mermaid" in _viz_family_fraud_zero()
        assert "```mermaid" in _viz_surgeon_overlap()
        assert "```mermaid" in _viz_surgeon_workload()
        assert "```mermaid" in _viz_therapy_overlap()
        assert "```mermaid" in _viz_therapy_normal()
        assert "```mermaid" in _viz_batch_billing_positive()
        assert "```mermaid" in _viz_batch_billing_zero()
        assert "```mermaid" in _viz_pharmacy_inventory()
        assert "```mermaid" in _viz_duplicate_testing()
        assert "```mermaid" in _viz_transfer_loop()
        assert "```mermaid" in _viz_consumables_match()
        assert "FDI" in _viz_dental_chart()
        assert "ICU" in _viz_icu_bundled()
        assert "```mermaid" in _viz_medication_hoarding()
        assert "```mermaid" in _viz_medication_hoarding_zero()
        assert "```mermaid" in _viz_high_value_ranking_positive()
        assert "```mermaid" in _viz_high_value_ranking_zero()
        assert "```mermaid" in _viz_drg_revolving()
