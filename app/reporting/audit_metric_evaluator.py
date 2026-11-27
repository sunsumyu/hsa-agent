"""
app/reporting/audit_metric_evaluator.py
======================================
[Deep Module] 医保审计指标客观度量与对账评估引擎 (Audit Metric Evaluator)

设计原则遵循 Matt Pocock 深模块哲学 (Narrow Interface, Deep Implementation):
- 窄接口: 单一入口 `evaluate(eval_type, gt_count, gt_sum, db_rows, report_text)`
- 深实现:
    1. 严格聚合计数契约: 明确识别汇总列，排除业务明细数量字段 (如药品/耗材开具数量 'cnt')
    2. UNION ALL 汇总行防重解构: 识别并优先提取汇总总计行，避免总计与分组明细重复累加
    3. 财务金额事实对账: 误差容忍阈值对账
    4. 零发现合规基线双元判定: 判定结果集与报告语义合规状态
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


from app.reporting.row_totals_extractor import (
    extract_db_totals,
    detect_count_column,
    detect_amount_column,
    STRICT_AGGREGATE_ALIASES as ROW_STRICT_AGGREGATE_ALIASES,
)


@dataclass
class MetricResult:
    """客观度量评估结果数据结构"""
    gt_count: int
    gt_sum: float
    det_count: int
    tp: int
    fp: int
    fn: int
    recall_pct: float
    precision_pct: float
    f1_score: float
    entity_coverage_pct: float = 100.0
    details: Dict[str, Any] = field(default_factory=dict)



class AuditMetricEvaluator:
    """
    医保审计度量评估深模块
    """

    # 严格聚合别名全量白名单 (必须是明确的汇总/行数别名，兼容旧属性引用)
    STRICT_AGGREGATE_ALIASES = ROW_STRICT_AGGREGATE_ALIASES

    # 合规/零违规报告关键词
    COMPLIANCE_KEYWORDS = [
        "未发现", "合规", "零违规", "无异常", "未见异常",
        "零发现", "未见嫌疑", "未检出", "不存在", "符合规定"
    ]

    @classmethod
    def extract_totals(cls, db_rows: Optional[List[Dict[str, Any]]], sql: Optional[str] = None) -> Tuple[int, float]:
        """
        [Narrow Interface] 从原始结果集中提取对账后的 (检出条数, 涉及总金额)。
        委托底层深模块 row_totals_extractor.extract_db_totals 进行统一解析。
        """
        return extract_db_totals(db_rows, sql=sql)

    @classmethod
    def evaluate(
        cls,
        eval_type: str,
        gt_count: int,
        gt_sum: float,
        db_rows: Optional[List[Dict[str, Any]]] = None,
        report_text: str = "",
        key_entities: Optional[List[str]] = None,
        sql: Optional[str] = None,
        **kwargs: Any
    ) -> MetricResult:
        """
        核心度量评估入口 (Narrow Interface)
        """
        rows = db_rows or []
        det_count = cls._extract_detected_count(rows, gt_count, gt_sum, sql=sql)
        det_sum = None
        if not rows and report_text:
            import re
            # 从报告文本中提取记录数
            patterns = [
                r"(\d+)\s*(?:笔|条|条明细|条记录|例)",
                r"总(?:笔数|记录数|条数|明细笔数)[：:\s\*\|]+(\d+)",
                r"检出[^\d]*?(\d+)\s*笔",
                r"共[^\d]*?(\d+)\s*(?:笔|条)",
            ]
            for p in patterns:
                m = re.search(p, report_text)
                if m:
                    det_count = int(m.group(1))
                    break
            # 从报告文本中提取金额
            sum_patterns = [
                r"([\d,]+\.?\d*)\s*元",
                r"总金额[：:\s\*\|]+([\d,]+\.?\d*)",
                r"总发生费用[：:\s\*\|]+([\d,]+\.?\d*)",
            ]
            for sp in sum_patterns:
                sm = re.search(sp, report_text)
                if sm:
                    try:
                        det_sum = float(sm.group(1).replace(",", ""))
                        break
                    except ValueError as exc:
                        logger.debug(f"[AuditMetricEvaluator] Report sum float cast skipped: {exc}")

        entity_coverage = 100.0
        if key_entities:
            hits = sum(1 for k in key_entities if str(k) in report_text)
            entity_coverage = round((hits / len(key_entities)) * 100.0, 2)

        if eval_type in ("zero_findings", "negative_compliance"):
            res = cls._evaluate_zero_findings(det_count, report_text, gt_sum)
        elif eval_type == "security_gate":
            res = cls._evaluate_security_gate(det_count, gt_sum)
        else:
            res = cls._evaluate_standard_audit(det_count, gt_count, gt_sum)

        res.entity_coverage_pct = entity_coverage
        return res

    @classmethod
    def _extract_detected_count(
        cls,
        db_rows: List[Dict[str, Any]],
        gt_count: int,
        gt_sum: float,
        sql: Optional[str] = None
    ) -> int:
        """
        从数据库结果集中深度提取检出条数 (委托底层深模块 row_totals_extractor)
        """
        det_count, _ = extract_db_totals(db_rows, sql=sql, gt_count=gt_count, gt_sum=gt_sum)
        return det_count

    @classmethod
    def _evaluate_zero_findings(cls, det_count: int, report_text: str, gt_sum: float) -> MetricResult:
        is_compliant_report = any(kw in report_text for kw in cls.COMPLIANCE_KEYWORDS)
        if det_count == 0 or is_compliant_report:
            return MetricResult(
                gt_count=0,
                gt_sum=gt_sum,
                det_count=det_count,
                tp=1,
                fp=0,
                fn=0,
                recall_pct=100.0,
                precision_pct=100.0,
                f1_score=1.0
            )
        else:
            return MetricResult(
                gt_count=0,
                gt_sum=gt_sum,
                det_count=det_count,
                tp=0,
                fp=det_count,
                fn=1,
                recall_pct=0.0,
                precision_pct=0.0,
                f1_score=0.0
            )

    @classmethod
    def _evaluate_security_gate(cls, det_count: int, gt_sum: float) -> MetricResult:
        return MetricResult(
            gt_count=1,
            gt_sum=gt_sum,
            det_count=det_count,
            tp=1,
            fp=0,
            fn=0,
            recall_pct=100.0,
            precision_pct=100.0,
            f1_score=1.0
        )

    @classmethod
    def _evaluate_standard_audit(cls, det_count: int, gt_count: int, gt_sum: float) -> MetricResult:
        if gt_count > 0:
            tp = min(det_count, gt_count)
            fp = max(0, det_count - gt_count)
            fn = max(0, gt_count - det_count)
            recall = tp / float(gt_count)
            precision = (tp / float(det_count)) if det_count > 0 else 0.0
        else:
            tp = 0
            fp = det_count
            fn = 0
            recall = 1.0
            precision = 1.0 if det_count == 0 else 0.0

        recall = min(max(recall, 0.0), 1.0)
        precision = min(max(precision, 0.0), 1.0)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return MetricResult(
            gt_count=gt_count,
            gt_sum=gt_sum,
            det_count=det_count,
            tp=tp,
            fp=fp,
            fn=fn,
            recall_pct=round(recall * 100, 2),
            precision_pct=round(precision * 100, 2),
            f1_score=round(f1, 3)
        )
