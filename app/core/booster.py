"""
[Matt Pocock Deep Module Facade] PrecisionBooster Facade.
Delegates hard metric calculation and evidence grounding to `hard_metric_calculator`,
and semantic alignment judging to `semantic_alignment_judge`.
Provides clean backwards-compatibility for existing consumers and tests.
"""
from typing import List, Dict, Any, Tuple, Optional
from app.core.container import LazyProxy

# Re-export DataExtractionError and calculator functions for backward compatibility
from app.core.guardrails.hard_metric_calculator import (
    DataExtractionError,
    calculate_hard_metrics as _calculate_hard_metrics,
    parse_table_to_rows as _parse_table_to_rows,
    detect_anomalous_consistency as _detect_anomalous_consistency,
    verify_evidence_grounding as _verify_evidence_grounding,
)
from app.core.guardrails.semantic_alignment_judge import (
    judge_semantic_alignment as _judge_semantic_alignment,
)


class PrecisionBooster:
    """物理计算助推器 Facade：实现审计数值的确定性计算与事实性守卫"""

    @staticmethod
    def calculate_hard_metrics(raw_data_str: str) -> Tuple[float, int, List[float]]:
        """计算硬指标与物理取证数值，委托至 hard_metric_calculator 深模块"""
        return _calculate_hard_metrics(raw_data_str)

    @staticmethod
    def parse_table_to_rows(raw_data_str: str) -> List[Dict[str, Any]]:
        """Markdown/JSON 原始字符串转结构化行列表，委托至 hard_metric_calculator 深模块"""
        return _parse_table_to_rows(raw_data_str)

    @staticmethod
    def detect_anomalous_consistency(rows_data: List[Dict[str, Any]]) -> Optional[str]:
        """笛卡尔积衍生计数爆炸防御，委托至 hard_metric_calculator 深模块"""
        return _detect_anomalous_consistency(rows_data)

    @staticmethod
    def verify_evidence_grounding(report_findings: List[Any], raw_data_list: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """证据溯源校验 (Fact-Check Pinning)，委托至 hard_metric_calculator 深模块"""
        return _verify_evidence_grounding(report_findings, raw_data_list)

    @staticmethod
    def verify_semantic_alignment(sql: str, report_text: str) -> Tuple[bool, str]:
        """上下文感知型语义一致性审计裁判，委托至 semantic_alignment_judge 深模块"""
        return _judge_semantic_alignment(sql, report_text)


# Backward-compatible alias, delegates to DI container
booster = LazyProxy("booster")
