"""
app/skills/sql_complexity_auditor.py
====================================
[Matt Pocock Deep Module] 基于 AST 的 SQL 算力代价与 ClickHouse 分区裁剪审计深模块。

职责内聚：
1. 识别涉及的 18GB 大表 (fqz_gz_jzsj_all_ql 等)
2. 扫描索引键过滤 (psn_no, setl_id)
3. 扫描时间分区键过滤 (setl_time, start_date, end_date 及 toYear 等函数包裹)
4. 多大表间 Heavy JOIN 笛卡尔积/OOM 算力防御拦截
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from app.core.registry.schema_registry import schema_registry


def audit_expression_complexity(expression: exp.Expression) -> None:
    """
    [基于 AST 的算力审计]
    从“个人过滤”转向“分区隔离与大表保护”。
    若发现严重算力超限、缺失分区裁剪或无索引跨大表关联，抛出 SQLComplexityError。
    """
    from app.skills.security import SQLComplexityError

    joins = list(expression.find_all(exp.Join))
    table_names = [(t.name or "").upper() for t in expression.find_all(exp.Table)]

    # 大表列表从 SchemaRegistry 读取
    main_table = schema_registry.get_main_table().upper()
    large_tables = [main_table, f"{main_table}_FIXED"]

    involves_large_table = any(t in large_tables for t in table_names)

    if involves_large_table:
        has_index_filter = False
        has_time_filter = False

        # 扩展谓词扫描：覆盖 EQ, In, GT, GTE, LT, LTE, Between
        full_sql_upper = str(expression).upper()
        for predicate in expression.find_all((exp.EQ, exp.In, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
            pred_str = str(predicate).upper()
            if "PSN_NO" in pred_str or "SETL_ID" in pred_str:
                has_index_filter = True
            if any(tf in pred_str for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                has_time_filter = True

        # Fallback: 函数包裹的时间条件（如 toYear(toDateTime(setl_time)) = 2024）
        if not has_time_filter:
            if any(tf in full_sql_upper for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                where_clause = expression.find(exp.Where)
                if where_clause and any(tf in str(where_clause).upper() for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                    has_time_filter = True

        is_heavy_join = False
        if joins:
            catalog_tables = {"FQZ_DRUG_MCS_INFO_LIST", "FQZ_ALL_YY_YD_1"}
            for join_node in joins:
                if hasattr(join_node.this, "name"):
                    join_table = (join_node.this.name or "").upper()
                    if join_table and (join_table in large_tables or join_table not in catalog_tables):
                        is_heavy_join = True
                        break

        if is_heavy_join and not has_index_filter:
            raise SQLComplexityError(
                "物理算力拦截：检测到大表间关联操作。为防止 OOM，必须显式提供 psn_no 过滤条件（Investigation 模式）。"
            )

        if not has_index_filter and not has_time_filter:
            raise SQLComplexityError(
                "物理算力拦截：在扫描 18GB 流水表执行 Discovery 任务时，必须显式提供 setl_time 或 start_date 时间区间（推荐 '2024-01-01' 起）以利用 ClickHouse 分区裁剪性能。"
            )
