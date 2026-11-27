"""
Red test for app/reporting/visualization_templates.py
Testing deep module extraction of Mermaid visualization template rendering.
"""
import pytest
from app.reporting.visualization_templates import render_audit_visualization


class TestVisualizationTemplatesDeepModule:
    def test_family_fraud_positive_rendered(self):
        result = render_audit_visualization("家族套保团伙", finding_count=3)
        assert "mermaid" in result
        assert "家庭共用特征层" in result or "family" in result.lower()

    def test_family_fraud_zero_rendered(self):
        result = render_audit_visualization("家族套保团伙", finding_count=0)
        assert "mermaid" in result
        assert "Theoretical Cluster Topology" in result or "协同聚类层" in result

    def test_surgeon_workload_rendered(self):
        result = render_audit_visualization("主刀医师连轴转物理极限", finding_count=0)
        assert "mermaid" in result
        assert "手术" in result or "时间轴" in result

    def test_surgeon_overlap_rendered(self):
        result = render_audit_visualization("主刀医师分身术重叠冲突", finding_count=2)
        assert "mermaid" in result
        assert "重叠" in result or "分身" in result or "冲突" in result

    def test_drg_revolving_rendered(self):
        result = render_audit_visualization("DRG分解住院假出院48小时再次入院", finding_count=1)
        assert "mermaid" in result
        assert "DRG" in result or "出院" in result

    def test_unrelated_returns_empty_string(self):
        result = render_audit_visualization("普通数据查询，无特殊专题", finding_count=0)
        assert result == ""
