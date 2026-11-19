"""
app/skills/audit_execution_pipeline.py
======================================
[Matt Pocock Deep Module] 医保审计核查执行流水线与多态报告调度器

核心职责：
1. 规则/算法双态 SQL 解析：协调确定性规则引擎与统计异常检测引擎的 SQL 生成，自动向下传递动态参数；
2. 执行取证结果规整：统一底层执行状态（错误字典、拦截熔断、空数据等），抹平各存储驱动与 SQL 工具的输出差异；
3. 多态取证报告分发：依据执行模式自动调度规则报告或算法报告渲染器；
4. 审计证据标准信封组装：提供标准化证据结构与日志追踪提示。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


class AuditExecutionPipeline:
    """医保审计执行流水线深模块"""

    def resolve_query_sql(
        self,
        target_id: str,
        extra_filters: Optional[Dict[str, Any]] = None,
        rule_engine_inst: Any = None,
        anomaly_detector_inst: Any = None,
    ) -> Tuple[Optional[str], bool]:
        """
        依次尝试从确定性规则库与统计异常算法库解析 SQL。
        返回: (sql, is_anomaly)
        """
        if rule_engine_inst is None:
            from app.skills.audit_rules import rule_engine
            re = rule_engine
        else:
            re = rule_engine_inst

        sql = re.get_rule_sql(target_id, extra_filters=extra_filters)
        if sql:
            return sql, False

        if anomaly_detector_inst is None:
            from app.skills.anomaly_algorithms import anomaly_detector
            ad = anomaly_detector
        else:
            ad = anomaly_detector_inst

        # 将动态过滤器传递给统计算法库，防止全表扫描导致超时与熔断
        sql = ad.get_algorithm_sql(target_id, extra_filters=extra_filters)
        if sql:
            return sql, True

        return None, False

    def normalize_evidence_result(
        self,
        raw_data: Any,
    ) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
        """
        规整底层执行函数返回的证据数据。
        返回: (is_success, error_message, normalized_list)
        """
        if isinstance(raw_data, dict) and raw_data.get("status") == "ERROR":
            err_msg = f"SQL Execution Failed: {raw_data.get('error_message')}"
            return False, err_msg, []

        if isinstance(raw_data, str) and "失败" in raw_data:
            err_msg = f"Execution blocked: {raw_data}"
            return False, err_msg, []

        if isinstance(raw_data, list):
            return True, None, raw_data

        return True, None, []

    def format_evidence_report(
        self,
        target_id: str,
        raw_data: List[Dict[str, Any]],
        is_anomaly: bool,
        rule_engine_inst: Any = None,
        anomaly_detector_inst: Any = None,
    ) -> str:
        """多态分发取证核查报告文本生成"""
        if is_anomaly:
            if anomaly_detector_inst is None:
                from app.skills.anomaly_algorithms import anomaly_detector
                ad = anomaly_detector
            else:
                ad = anomaly_detector_inst
            return ad.format_anomaly_report(target_id, raw_data)
        else:
            if rule_engine_inst is None:
                from app.skills.audit_rules import rule_engine
                re = rule_engine
            else:
                re = rule_engine_inst
            return re.format_violation_report(target_id, raw_data)

    def assemble_audit_payload(
        self,
        report_text: str,
        raw_data: List[Dict[str, Any]],
        methodology: str,
        sql: str,
        is_anomaly: bool,
    ) -> Dict[str, Any]:
        """组装标准审计证据输出信封"""
        count = len(raw_data)
        engine_type = "Anomaly" if is_anomaly else "Rule"
        return {
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "methodology": methodology,
            "sql_logic": sql,
            "trace_hint": f"[{engine_type} Engine] {methodology} | 命中 {count} 条记录",
        }


# 单例默认实例
audit_execution_pipeline = AuditExecutionPipeline()
