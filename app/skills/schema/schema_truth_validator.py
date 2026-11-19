"""
app/skills/schema_truth_validator.py
====================================
[Matt Pocock Deep Module] SQL 字段与函数物理真理对撞及幻觉智能纠错深模块。

职责内聚：
1. 精准提取当前查询涉及的底层物理业务表 (排除 CTE 别名与 system 系统库)
2. 基于 SchemaRegistry 与 FieldKG 对撞物理真实字段，拦截幻觉列
3. 对高频幻觉字段与虚拟指标提供语义纠错建议
4. 校验常用 ClickHouse 聚合与窗口函数，拦截不支持的函数并做方言引导
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from loguru import logger
from app.core.registry.schema_registry import schema_registry


COMMON_HALLUCINATIONS: dict[str, str] = {
    "fee_amt": "medfee_sumamt",
    "total_fee": "medfee_sumamt",
    "amount": "medfee_sumamt",
    "pay_amount": "fund_pay_sumamt",
    "fund_amt": "fund_pay_sumamt",
    "hosp_code": "fixmedins_code",
    "hospital_id": "fixmedins_code",
    "hosp_name": "fixmedins_name",
    "hospital_name": "fixmedins_name",
    "patient_id": "psn_no",
    "patient_name": "psn_name",
    "item_name": "hilist_name",
    "drug_name": "hilist_name",
    "det_item_name": "hilist_name",
    "medical_category": "med_type",
    "type_name": "med_type",
    "settlement_time": "setl_time",
    "settle_time": "setl_time",
    "gender": "gend",
    "sex": "gend",
    # ── 虚拟计算指标：非物理字段，需通过 SQL 公式计算 ──
    "vix": "非物理字段。变异指数需计算: stddevPop(medfee_sumamt)/avg(medfee_sumamt) AS vix",
    "variation_index": "非物理字段。变异指数需计算: stddevPop(medfee_sumamt)/avg(medfee_sumamt) AS variation_index",
    "overlap_hours": "非物理字段。需计算: dateDiff('hour', greatest(a.start_date, b.start_date), least(a.end_date, b.end_date)) AS overlap_hours",
    "department_id": "非物理字段。科室信息在 dise_name 或 fixmedins_name 中",
    "dept_id": "非物理字段。科室信息在 dise_name 或 fixmedins_name 中",
    "visit_count": "非物理字段。需计算: COUNT(*) AS visit_count",
    "admission_count": "非物理字段。需计算: COUNT(*) AS admission_count",
    "age": "非物理字段。需计算: dateDiff('year', toDate(brdy), today()) AS age (brdy=出生日期字段)",
    "los": "非物理字段。住院天数需计算: dateDiff('day', start_date, end_date) AS los",
    "length_of_stay": "非物理字段。住院天数需计算: dateDiff('day', start_date, end_date) AS length_of_stay",
}

# ClickHouse 常用内置函数白名单
ALLOWED_FUNCTIONS: set[str] = {
    "count", "sum", "avg", "min", "max", "toyear", "tomonth", "todatetime", "todate",
    "datediff", "ifnull", "arraystringconcat", "groupuniqarray", "multisearchany",
    "substring", "countdistinct", "grouparray", "tostring", "toint64", "coalesce",
    "any", "uniq", "round", "length", "format", "if", "multiif", "greatest", "least",
    "and", "or", "not", "anonymous", "anonymousaggfunc",
    "row_number", "laginframe", "lead", "lag", "rank", "dense_rank",
}


def suggest_field_replacement(hallucinated: str) -> str:
    """
    对幻觉字段做模糊匹配，返回可能的正确物理字段建议
    """
    h = hallucinated.lower().strip()
    if h in COMMON_HALLUCINATIONS:
        correct = COMMON_HALLUCINATIONS[h]
        return f"建议替换: `{hallucinated}` → `{correct}`。"
    # 子串匹配
    for wrong, correct in COMMON_HALLUCINATIONS.items():
        if wrong in h or h in wrong:
            return f"建议替换: `{hallucinated}` → `{correct}`。"
    return "无法自动推测正确字段。"


def validate_column_and_function_existence(expression: exp.Expression) -> None:
    """
    [物理真理对撞] 基于 AST 执行严格的表级字段与函数校验。
    精准对撞 SchemaRegistry 中的物理表列，拦截幻觉列与非法函数。
    """
    from app.skills.security import SecurityViolationError
    from app.infra.neo4j_manager import field_kg

    # 1. 提取当前 SQL 涉及的所有物理业务表 (排除 CTE 临时表以及系统元数据库表)
    cte_names = set()
    for cte in expression.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias.lower())

    tables = []
    for t in expression.find_all(exp.Table):
        t_name = t.name.lower()
        is_sys = bool(t.db and t.db.lower() in {"system", "information_schema"})
        if not is_sys and t_name not in cte_names:
            tables.append(t_name)

    # 若纯为系统元数据表探查（如 system.columns 或 information_schema.columns），跳过业务字段对撞
    if not tables:
        return

    # 2. 构建针对当前表的“物理真理库” (通过 SchemaRegistry 统一深接缝)
    physical_columns = set()
    for t_name in tables:
        physical_columns.update(schema_registry.get_table_columns(t_name))

    # 3. 常见聚合函数与本地别名
    local_aliases = {alias.alias.lower() for alias in expression.find_all(exp.Alias)}

    for node in expression.walk():
        # 校验字段 (exp.Column)
        if isinstance(node, exp.Column):
            col_name = node.name.lower()
            # 排除别名和标准计算列
            if col_name in local_aliases or col_name in {"*", "1"}:
                continue

            # 核心拦截：如果不在当前表的物理列中，且 FieldKG 无法映射
            if col_name not in physical_columns:
                resolved = field_kg.resolve(col_name)
                if not resolved:
                    suggestion = suggest_field_replacement(col_name)
                    logger.warning(f"🛡️ [SchemaTruthValidator] 物理字段拦截: {tables} -> `{col_name}`")
                    raise SecurityViolationError(
                        f"【物理拦截】字段 `{col_name}` 在当前表 {tables} 中不存在！"
                        f"{suggestion} "
                        f"请通过 `lookup_medical_schema` 工具获取正确物理字段。"
                    )

        # 校验函数 (exp.Func)
        elif isinstance(node, exp.Func):
            func_name = node.key.lower()
            if func_name not in ALLOWED_FUNCTIONS:
                # 针对 year/month 这种典型幻觉做专门引导
                if func_name in {"year", "month", "day"}:
                    raise SecurityViolationError(
                        f"【物理拦截】检测到非法函数 `{func_name}()`。ClickHouse 不支持此语法。"
                        f"请改用 `toYear()`, `toMonth()` 或直接使用日期字段范围过滤。"
                    )
                logger.warning(f"⚠️ [SECURITY] 使用了非标准函数: {func_name}")
