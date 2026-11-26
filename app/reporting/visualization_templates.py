"""
app/reporting/visualization_templates.py
========================================
Audit Visualization Templates Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates 13+ specialized Mermaid
charts and audit topology visualizations behind a clean, single-entry interface:
`render_audit_visualization(user_question: str, finding_count: int) -> str`.

Extensible Architecture:
Uses `AuditVisualizationRegistry` with pluggable `VisualizationTopic` strategies,
eliminating monolithic if-elif branches while preserving 100% backward compatibility.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from app.reporting.visualization_templates_core import (
    _viz_batch_billing_positive,
    _viz_batch_billing_zero,
    _viz_duplicate_testing,
    _viz_family_fraud_positive,
    _viz_family_fraud_zero,
    _viz_pharmacy_inventory,
    _viz_surgeon_overlap,
    _viz_surgeon_workload,
    _viz_therapy_normal,
    _viz_therapy_overlap,
    _viz_transfer_loop,
)
from app.reporting.visualization_templates_extended import (
    _viz_consumables_match,
    _viz_dental_chart,
    _viz_drg_revolving,
    _viz_high_value_ranking_positive,
    _viz_high_value_ranking_zero,
    _viz_icu_bundled,
    _viz_medication_hoarding,
    _viz_medication_hoarding_zero,
)


@dataclass
class VisualizationTopic:
    """反欺诈可视化专题策略定义"""
    topic_id: str
    keywords: List[str]
    renderer: Callable[[int, str], str]
    matcher: Optional[Callable[[str], bool]] = None

    def matches(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        if self.matcher is not None:
            return self.matcher(q)
        return any(kw in q for kw in self.keywords)


_DEFAULT_TOPIC_SPECS = (
    (
        "family_fraud",
        ["家族", "套保", "团伙", "地址", "手机号", "电话", "画出来", "关系网", "图谱"],
        lambda count, q: _viz_family_fraud_positive() if count > 0 else _viz_family_fraud_zero(),
    ),
    (
        "surgeon_timeline",
        ["手术", "主刀", "时长", "时间轴", "资质", "连轴转", "分身术", "冲突", "重叠"],
        lambda count, q: _viz_surgeon_overlap() if ("分身" in q or "冲突" in q or "重叠" in q) else _viz_surgeon_workload(),
    ),
    (
        "therapy_overlap",
        ["理疗", "康复", "手法", "按摩", "推拿"],
        lambda count, q: _viz_therapy_overlap() if count > 0 else _viz_therapy_normal(),
    ),
    (
        "batch_billing",
        ["批量", "连续", "快速", "秒级", "时序异常", "刷卡", "刷单"],
        lambda count, q: _viz_batch_billing_positive() if count > 0 else _viz_batch_billing_zero(),
    ),
    ("pharmacy_inventory", ["进销存", "库存倒挂", "负库存", "无中生有", "大药房"], lambda count, q: _viz_pharmacy_inventory()),
    ("duplicate_testing", ["重复检查", "检查结果互认", "增强ct", "核磁共振", "大型检查"], lambda count, q: _viz_duplicate_testing()),
    ("malicious_transfer", ["转院", "盈亏临界点", "推诿", "肿瘤", "重症"], lambda count, q: _viz_transfer_loop()),
    ("consumables_match", ["不用工具", "耗材", "匹配", "配对", "钛板", "钛钉", "耗材缺失"], lambda count, q: _viz_consumables_match()),
    ("dental_chart", ["牙", "拔牙", "口腔"], lambda count, q: _viz_dental_chart()),
    ("icu_bundled", ["icu", "重症", "双头", "重复收费", "抢救", "打包"], lambda count, q: _viz_icu_bundled()),
    (
        "medication_hoarding",
        ["跨院", "重复开药", "慢病", "时间窗", "滚动", "囤药"],
        lambda count, q: _viz_medication_hoarding() if count > 0 else _viz_medication_hoarding_zero(),
    ),
    ("drg_revolving", ["drg", "假出院", "出院", "入院", "48小时", "再次"], lambda count, q: _viz_drg_revolving()),
    (
        "high_value_ranking",
        ["大额", "排名", "结算金额", "最高", "金额排名", "频繁", "异常案件"],
        lambda count, q: _viz_high_value_ranking_positive() if count > 0 else _viz_high_value_ranking_zero(),
    ),
)


class AuditVisualizationRegistry:
    """反欺诈可视化模板策略注册中心深模块"""

    def __init__(self, register_defaults: bool = True):
        self._topics: List[VisualizationTopic] = []
        if register_defaults:
            self._register_default_topics()

    def register(self, topic: VisualizationTopic, prepend: bool = False) -> None:
        """注册新可视化专题策略"""
        if prepend:
            self._topics.insert(0, topic)
        else:
            self._topics.append(topic)

    def get_registered_topics(self) -> List[str]:
        """获取所有已注册的专题 ID 列表"""
        return [t.topic_id for t in self._topics]

    def render(self, user_question: str, finding_count: int) -> str:
        """
        根据用户查询与发现命中数匹配并渲染 Mermaid 可视化块。
        未匹配则安全返回空字符串。
        """
        if not user_question:
            return ""
        q = user_question.lower()
        for topic in self._topics:
            if topic.matches(q):
                return topic.renderer(finding_count, q)
        return ""

    def _register_default_topics(self) -> None:
        """注册内置的医保反欺诈 Mermaid 可视化专题"""
        for topic_id, keywords, renderer in _DEFAULT_TOPIC_SPECS:
            self.register(VisualizationTopic(topic_id=topic_id, keywords=keywords, renderer=renderer))


# 全局单例策略注册中心
visualization_registry = AuditVisualizationRegistry()


def render_audit_visualization(user_question: str, finding_count: int) -> str:
    """
    Return a Mermaid visualization block matching the audit topic and finding outcome.
    Returns empty string if no visualization template matches the user question.
    """
    return visualization_registry.render(user_question, finding_count)
