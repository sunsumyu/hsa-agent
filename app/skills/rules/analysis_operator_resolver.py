"""
app/skills/analysis_operator_resolver.py
========================================
分析算子语义解析与图谱安全深模块（Deep Module）

职责：
- 审计规则与异常算法语义映射路由
- 业务容差门限计算
- 图谱空间隔离与越界关系表物理拦截校验
- 联邦实体提取与去重清洗
"""

from __future__ import annotations

import re
from typing import Dict, Any, List, Optional


def resolve_audit_rule_id(rule_id: str) -> str:
    """
    根据规则标识或关键词映射到物理违规规则 ID。
    """
    if not rule_id:
        return ""
    rule_key = str(rule_id).upper()
    if "GENDER" in rule_key or "性别" in rule_key:
        return "GENDER_CONFLICT"
    elif "DRUG" in rule_key or "购药" in rule_key:
        return "HIGH_FREQ_DRUG_PURCHASE"
    elif "DECOMPOSITION" in rule_key or "分解" in rule_key:
        return "DECOMPOSITION_HOSPITALIZATION"
    elif "CROSS" in rule_key or "重复住院" in rule_key or "同时住院" in rule_key:
        return "CROSS_HOSPITAL_OVERLAP"
    elif "REPEAT_BILLING" in rule_key or "重复收费" in rule_key:
        return "REPEAT_BILLING_DETECTOR"
    elif "CONTACT_SHARING" in rule_key or "联系方式" in rule_key:
        return "CONTACT_SHARING"
    return rule_key


def resolve_anomaly_algorithm_id(algorithm_id: str) -> str:
    """
    根据算法标识或关键词映射到物理异常检测算法 ID。
    """
    if not algorithm_id:
        return ""
    algo_key = str(algorithm_id).upper()
    if "VIX" in algo_key or "变异" in algo_key:
        return "VIX_ANOMALY_SCAN"
    elif "OUTLIER" in algo_key or "离群" in algo_key:
        return "STATISTICAL_OUTLIER_DETECTOR"
    elif "CLUSTER" in algo_key or "聚集" in algo_key or "联系方式" in algo_key:
        return "CLUSTER_ENCOUNTER_DETECTOR"
    elif "MAD" in algo_key or "稳健" in algo_key:
        return "ROBUST_MAD_DETECTOR"
    return algo_key


def get_operator_tolerance(target_operator: str, default: int = 1000) -> int:
    """
    计算特定算子的执行业务容差。
    """
    op = str(target_operator).upper()
    if "REPEAT_BILLING" in op:
        return 50000
    if "VIX" in op or "OUTLIER" in op or "CLUSTER" in op or "MAD" in op:
        return default if default != 1000 else 20000
    return default


def validate_cypher_spatial_isolation(cypher: str) -> Optional[str]:
    """
    图数据库物理隔离校验：
    如果在 Cypher 查询中检测到关系型物理数据表（如以 fqz_ 开头的表），返回错误说明，否则返回 None。
    """
    if not cypher:
        return None
    relational_tables = re.findall(r"\bfqz_[a-z0-9_]+\b", cypher, re.IGNORECASE)
    if relational_tables:
        return (
            f"物理拦截：在 Cypher 语句中发现了关系型表名 {relational_tables}。"
            "图数据库（Neo4j）中不包含物理表，仅包含节点（如 Patient, Contact）和关系（如 HAS_CONTACT）。"
            "请重新规划，在 [RELATIONAL_ZONE] 使用 execute_audit_sql 查询该表。"
        )
    return None


def extract_entity_ids(records: List[Dict[str, Any]], return_key: str = "") -> List[str]:
    """
    从图谱查询结果记录集中提取实体 ID 列表，自动去重并过滤空值。
    """
    if not records:
        return []

    ids: List[str] = []
    for r in records:
        if return_key and return_key in r:
            val = r[return_key]
        else:
            val = list(r.values())[0] if r else None
        if val is not None and str(val).strip():
            ids.append(str(val).strip())

    # 保持相对稳定去重
    seen = set()
    unique_ids = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            unique_ids.append(x)
    return unique_ids
