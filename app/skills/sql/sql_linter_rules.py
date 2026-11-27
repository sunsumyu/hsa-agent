"""
app/skills/sql_linter_rules.py
==============================
[Matt Pocock Deep Module] SQL 静态治理规则链深模块

核心职责：
1. 主键唯一流水号聚合拦截（如 MSG_ID, REC_ID 等）
2. 动态业务规则拦截（基于 configs/audit_governance.yaml 的目录模糊匹配与时间维度冲突）
3. 关联关系与笛卡尔积拦截（AST 级检测无条件 JOIN 与无过滤 CROSS JOIN）
4. 统一组装为端到端运行的 run_sql_linter_pipeline
"""

from __future__ import annotations
import os
import re
import yaml
from typing import Tuple, Dict, Any, Optional
from sqlglot import exp, parse_one
from loguru import logger


def load_governance_config(config_path: str = "configs/audit_governance.yaml") -> Dict[str, Any]:
    """加载通用审计治理红线配置"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"[SQLLinter] 审计治理配置加载失败: {e}")
    return {}


def validate_pk_group_by(sql: str) -> Tuple[bool, str]:
    """基础架构校验：主键聚合拦截（禁止按系统底层单行流水物理 ID，如 MSG_ID, REC_ID 分组）"""
    sql_upper = str(sql or "").upper()
    if "GROUP BY" in sql_upper and any(agg in sql_upper for agg in ["COUNT", "SUM", "AVG"]):
        forbidden_pks = ["MSG_ID", "REC_ID"]
        gb_clause = sql_upper.split("GROUP BY")[-1]
        for delim in ["ORDER BY", "HAVING", "LIMIT", "WINDOW", "SETTINGS", ";"]:
            if delim in gb_clause:
                gb_clause = gb_clause.split(delim)[0]
        for pk in forbidden_pks:
            if re.search(rf"\b{pk}\b", gb_clause):
                return False, f"❌ [架构拦截] 聚合查询禁止按唯一流水记录 ID `{pk}` 分组。"
    return True, ""


def validate_dynamic_governance(sql: str, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """动态业务规则拦截（从治理配置加载，包含模糊匹配红线与时间维度准确性校验）"""
    sql_upper = str(sql or "").upper()
    cfg = config if config is not None else load_governance_config()
    rules = cfg.get("interception_rules", [])

    for rule in rules:
        rule_id = rule.get("id")
        # 1. 模糊匹配拦截逻辑
        if rule_id == "no_fuzzy_matching":
            keywords = rule.get("keywords", [])
            if "LIKE" in sql_upper and any(kw.upper() in sql_upper for kw in keywords):
                return False, f"❌ [治理拦截] {rule.get('name')}: {rule.get('description')}"
        
        # 2. 时间维度拦截逻辑
        if rule_id == "temporal_dimension_check":
            triggers = rule.get("trigger_keywords", [])
            if any(kw.upper() in sql_upper for kw in triggers):
                forbidden = rule.get("forbidden_fields", [])
                mandatory = rule.get("mandatory_fields", [])
                if any(f.upper() in sql_upper for f in forbidden) and not any(m.upper() in sql_upper for m in mandatory):
                    return False, f"❌ [维度拦截] {rule.get('name')}: {rule.get('description')}"

    return True, ""


def validate_join_cartesian(sql: str) -> Tuple[bool, str]:
    """通用安全校验：AST 级 JOIN 关联条件与笛卡尔积校验"""
    sql_upper = str(sql or "").upper()
    try:
        parsed = parse_one(sql, read="clickhouse")
        if parsed:
            for j in parsed.find_all(exp.Join):
                is_cross = (getattr(j, "kind", "") or "").upper() == "CROSS"
                has_condition = bool(j.args.get("on") or j.args.get("using"))
                if not is_cross and not has_condition:
                    return False, "❌ [安全拦截] JOIN 语句缺失关联条件，禁止执行潜在的笛卡尔积查询。"
                elif is_cross and not has_condition:
                    select_parent = j.find_ancestor(exp.Select)
                    has_where = bool(select_parent and select_parent.args.get("where"))
                    if not has_where:
                        return False, "❌ [安全拦截] CROSS JOIN 语句缺失 WHERE 关联过滤条件，禁止执行无界笛卡尔积查询。"
    except Exception:
        if "JOIN" in sql_upper and "CROSS JOIN" not in sql_upper and " ON " not in sql_upper and " USING " not in sql_upper:
            return False, "❌ [安全拦截] JOIN 语句缺失关联条件，禁止执行潜在的笛卡尔积查询。"

    return True, ""


def run_sql_linter_pipeline(sql: str) -> Tuple[bool, str]:
    """统一执行链式静态治理检查"""
    # 1. 唯一主键分组检查
    ok, err = validate_pk_group_by(sql)
    if not ok:
        return False, err

    # 2. 动态业务规则拦截
    ok, err = validate_dynamic_governance(sql)
    if not ok:
        return False, err

    # 3. 笛卡尔积关联校验
    ok, err = validate_join_cartesian(sql)
    if not ok:
        return False, err

    return True, ""
