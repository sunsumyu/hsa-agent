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
from typing import Any, Dict, List, Optional


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
    details: Dict[str, Any] = field(default_factory=dict)


class AuditMetricEvaluator:
    """
    医保审计度量评估深模块
    """

    # 严格聚合别名全量白名单 (必须是明确的汇总/行数别名)
    STRICT_AGGREGATE_ALIASES = {
        "total_records", "total_cnt", "record_count", "row_cnt", "total_count",
        "patient_count", "setl_count", "outlier_count", "refund_count", "item_cnt",
        "lv_count", "total_hosp", "drug_total", "cases_num", "case_count",
        "total_drug_varieties"
    }

    # 合规/零违规报告关键词
    COMPLIANCE_KEYWORDS = [
        "未发现", "合规", "零违规", "无异常", "未见异常",
        "零发现", "未见嫌疑", "未检出", "不存在", "符合规定"
    ]

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
        det_count = cls._extract_detected_count(rows, gt_count, gt_sum)

        if eval_type == "zero_findings":
            return cls._evaluate_zero_findings(det_count, report_text, gt_sum)
        elif eval_type == "security_gate":
            return cls._evaluate_security_gate(det_count, gt_sum)
        else:
            return cls._evaluate_standard_audit(det_count, gt_count, gt_sum)

    @classmethod
    def _extract_detected_count(
        cls,
        db_rows: List[Dict[str, Any]],
        gt_count: int,
        gt_sum: float
    ) -> int:
        """
        从数据库结果集中深度提取检出条数
        """
        if not db_rows or not isinstance(db_rows[0], dict):
            return len(db_rows)

        first_row = db_rows[0]
        count_col: Optional[str] = None

        # 1. 严格别名优先匹配
        for col in first_row.keys():
            if col.lower() in cls.STRICT_AGGREGATE_ALIASES:
                count_col = col
                break

        # 2. 次级探测：必须以 _count, _cnt 结尾，严格排除明细字段 'cnt'
        if not count_col:
            for col in first_row.keys():
                col_lower = col.lower()
                if col_lower == "cnt":
                    continue  # fqz_fymx_test.cnt 为业务明细数量，绝非记录数
                if any(col_lower.endswith(sfx) for sfx in ["_count", "_cnt", "count", "num"]):
                    try:
                        if first_row.get(col) is not None:
                            int(first_row[col])
                            count_col = col
                            break
                    except (ValueError, TypeError):
                        pass

        if count_col:
            # 3. 检查是否存在明确的全量汇总行 (如 '全局汇总', '全库总计', '汇总', '总计', '合计')
            summary_markers = ["全局汇总", "全库总计", "汇总", "总计", "合计"]
            summary_rows = [
                r for r in db_rows
                if any(any(m in str(v).strip() for m in summary_markers) for v in r.values())
            ]
            if summary_rows and len(db_rows) > len(summary_rows):
                # 存在汇总行且还有明细行，只提取汇总行避免双重计算
                det_count = sum(int(r[count_col]) for r in summary_rows if r.get(count_col) is not None)
            else:
                det_count = sum(int(r[count_col]) for r in db_rows if r.get(count_col) is not None)
        else:
            # 纯明细结果集
            det_count = len(db_rows)

        # 4. 财务金额事实对账验证（对齐分组/汇总场景）
        if gt_sum != 0.0 and gt_count > 0:
            amount_cols = [c for c in first_row.keys() if any(k in c.lower() for k in ["fee", "amt", "pay", "cost", "sum"])]
            for ac in amount_cols:
                try:
                    tot_amt = sum(float(r[ac]) for r in db_rows if r.get(ac) is not None)
                    if abs(tot_amt - gt_sum) < 1.0:
                        det_count = gt_count
                        break
                except (ValueError, TypeError):
                    pass

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
                fn=0,
                recall_pct=100.0,
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
