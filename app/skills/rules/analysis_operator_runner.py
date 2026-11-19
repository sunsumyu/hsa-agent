"""
app/skills/analysis_operator_runner.py
======================================
审计规则与统计异常算子执行引擎（Deep Module）

职责：
- 规则算子与异常检测算子的标准执行流
- 自动解析算子标识与计算业务容差
- 统一异步 SQL 执行与异常阻断处理
- 规整违规与异常报告并封装标准证据 JSON
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional
from loguru import logger

from app.skills.analysis_operator_resolver import (
    resolve_audit_rule_id,
    resolve_anomaly_algorithm_id,
    get_operator_tolerance,
)


async def execute_rule_operator(
    rule_id: str,
    extra_filters: Optional[Dict[str, str]] = None,
    rule_eng: Any = None,
    sql_executor: Optional[Callable[..., Any]] = None,
) -> str:
    """
    执行预定义物理违规规则算子流水线。
    """
    if not rule_id:
        return "Error: rule_id is required."

    rule_key = str(rule_id).upper()
    logger.info(f"🔨 [RUNNER] 执行物理违规规则引擎: {rule_id}")

    target_rule = resolve_audit_rule_id(rule_key)

    if rule_eng is None:
        from app.skills.audit_rules import rule_engine
        engine = rule_engine
    else:
        engine = rule_eng

    sql = engine.get_rule_sql(target_rule, extra_filters=extra_filters)
    if not sql:
        return json.dumps({
            "report": f"未找到匹配的审计算子: {rule_id}",
            "evidence_count": 0,
            "raw_evidence": [],
        }, ensure_ascii=False)

    if sql_executor is None:
        from app.skills.sql_execution_pipeline import execute_audit_sql_pipeline
        executor = execute_audit_sql_pipeline
    else:
        executor = sql_executor


    try:
        tolerance = get_operator_tolerance(target_rule, default=1000)
        raw_data = await executor(sql, return_raw=True, tolerance=tolerance)

        if isinstance(raw_data, str) and "失败" in raw_data:
            return json.dumps({
                "report": f"物理引擎执行受阻: {raw_data}",
                "evidence_count": 0,
                "raw_evidence": [],
            }, ensure_ascii=False)

        count = len(raw_data) if isinstance(raw_data, list) else 0
        report_text = engine.format_violation_report(target_rule, raw_data)

        return json.dumps({
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "sql_logic": sql,
            "trace_hint": f"[规则引擎] 触发算子 {target_rule}，物理库命中 {count} 条违规证据",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"规则引擎执行异常: {e}")
        return json.dumps({
            "report": "物理探测异常",
            "evidence_count": 0,
            "error": str(e),
            "raw_evidence": [],
            "sql_logic": sql,
            "trace_hint": f"[规则引擎] {rule_id} 执行异常",
        }, ensure_ascii=False)


async def execute_anomaly_operator(
    algorithm_id: str,
    threshold: float = 0.95,
    detector: Any = None,
    sql_executor: Optional[Callable[..., Any]] = None,
) -> str:
    """
    运行统计学异常检测算法流水线。
    """
    if not algorithm_id:
        return "Error: algorithm_id is required."

    algo_key = str(algorithm_id).upper()
    logger.info(f"📊 [RUNNER] 执行物理异常检测算子: {algorithm_id}")

    target_algo = resolve_anomaly_algorithm_id(algo_key)

    if detector is None:
        from app.skills.anomaly_algorithms import anomaly_detector
        detector_inst = anomaly_detector
    else:
        detector_inst = detector

    sql = detector_inst.get_algorithm_sql(target_algo)
    if not sql:
        return json.dumps({
            "report": f"未找到匹配的算法算子: {algorithm_id}",
            "evidence_count": 0,
            "raw_evidence": [],
        }, ensure_ascii=False)

    if sql_executor is None:
        from app.skills.sql_execution_pipeline import execute_audit_sql_pipeline
        executor = execute_audit_sql_pipeline
    else:
        executor = sql_executor


    try:
        tolerance = get_operator_tolerance(target_algo, default=20000)
        raw_data = await executor(sql, return_raw=True, tolerance=tolerance)

        if isinstance(raw_data, str) and "失败" in raw_data:
            return json.dumps({
                "report": f"物理算法执行受阻: {raw_data}",
                "evidence_count": 0,
                "raw_evidence": [],
            }, ensure_ascii=False)

        count = len(raw_data) if isinstance(raw_data, list) else 0
        report_text = detector_inst.format_anomaly_report(target_algo, raw_data)

        return json.dumps({
            "report": report_text,
            "evidence_count": count,
            "raw_evidence": raw_data,
            "sql_logic": sql,
            "trace_hint": f"[异常算法] 触发算子 {target_algo}，物理库命中 {count} 条异常线索",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"算法引擎执行异常: {e}")
        return json.dumps({
            "report": "物理探测异常",
            "evidence_count": 0,
            "error": str(e),
            "raw_evidence": [],
            "sql_logic": sql,
            "trace_hint": f"[异常算法] {algorithm_id} 执行异常",
        }, ensure_ascii=False)
