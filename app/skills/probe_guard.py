"""
app/skills/probe_guard.py
=========================
[Phase 3.4] SQL probe query detection.

Extracted from coder_agent.py. Identifies "probe" SQL queries that exist
only to explore schema or count rows, rather than executing the core audit.
The agent must bypass probes and go straight to the real audit SQL.
"""

from typing import List
from loguru import logger
import re

# Structural whitelist: these keywords indicate complex analytical SQL
# and should ALWAYS be exempt from probe classification, regardless of GROUP BY.
STRUCTURAL_WHITELIST: List[str] = [
    "WITH ",
    "CASE WHEN",
    "UNION ALL",
    "UNION ",
    "OVER ",
    "OVER(",
    "COUNTIF(",
    "SUMIF(",
    "AVGIF(",
    "MAXIF(",
    "MINIF(",
    "IF(",
    "IF (",
]

# Aggregate whitelist: these statistical keywords are only exempt when
# the query also has GROUP BY (i.e., dimensional analysis, not pure baseline).
# Without GROUP BY, they are pure baseline queries classified as probes.
AGGREGATE_WHITELIST: List[str] = [
    "QUANTILE",
    "PERCENTILE",
    "STDDEV",
    "VARIANCE",
    "MEDIAN",
    "CORR(",
    "QUANTILEEXACT",
]


def is_probe_query(sql: str) -> bool:
    """
    Determine whether a SQL string is a metadata/probe query.

    Returns True for: SHOW/DESC/EXPLAIN, bare COUNT(*) without JOIN/GROUP BY,
    DISTINCT dictionary lookups, short no-JOIN queries without analytical clauses,
    and pure baseline statistical queries (quantile/avg without GROUP BY).

    Returns False for: empty (treated as probe at call sites), queries with
    structural constructs (WITH/CTE, CASE WHEN, UNION ALL), aggregate analysis
    WITH GROUP BY, and any SQL with JOIN or complex analytical constructs.
    """
    if not sql:
        return True
    sql_upper = sql.upper().strip()

    has_group_by = "GROUP BY" in sql_upper
    has_join = "JOIN" in sql_upper

    # 0a. Structural whitelist: always exempt (indicates complex analytical SQL)
    if any(kw in sql_upper for kw in STRUCTURAL_WHITELIST):
        logger.debug(f"[ProbeGuard] structural whitelist exemption: {sql[:80]}...")
        return False

    # 0b. Aggregate whitelist: only exempt with GROUP BY (dimensional analysis)
    if has_group_by and any(kw in sql_upper for kw in AGGREGATE_WHITELIST):
        logger.debug(f"[ProbeGuard] aggregate whitelist with GROUP BY: {sql[:80]}...")
        return False

    # [V178.10] Pure baseline statistical query detection
    # If query only contains statistical aggregates (quantile/avg/median/stddev)
    # without GROUP BY or JOIN, it is a baseline query — mark as probe
    baseline_patterns = [
        r'SELECT\s+QUANTILE\s*\([^)]+\)\s*\([^)]+\)',  # quantile(0.95)(column)
        r'SELECT\s+AVG\s*\([^)]+\)',                   # avg(column)
        r'SELECT\s+MEDIAN\s*\([^)]+\)',                # median(column)
        r'SELECT\s+STDDEV\s*\([^)]+\)',                # stddev(column)
        r'SELECT\s+PERCENTILE\s*\([^)]+\)',            # percentile(column)
    ]
    is_pure_baseline = any(re.search(p, sql_upper) for p in baseline_patterns)

    if is_pure_baseline and not has_group_by and not has_join:
        logger.debug(f"[ProbeGuard] pure baseline query detected: {sql[:80]}...")
        return True

    # [V178.10] avg()/sum() special handling: only exempt with GROUP BY or JOIN, or business filters
    if "AVG(" in sql_upper or "SUM(" in sql_upper or "AVERAGE(" in sql_upper:
        if has_group_by or has_join:
            logger.debug(f"[ProbeGuard] avg/sum with GROUP BY/JOIN: {sql[:80]}...")
            return False
        else:
            if "WHERE" in sql_upper and any(term in sql_upper for term in ["LIKE", "IN (", "IN(", "AND", "OR", "MULTISEARCH", ">", "<", "=", "!=", ">=", "<=", "BETWEEN"]):
                logger.debug(f"[ProbeGuard] aggregate with business filters: {sql[:80]}...")
                return False
            logger.debug(f"[ProbeGuard] pure avg/sum baseline: {sql[:80]}...")
            return True

    # 1. Metadata probes (DESCRIBE, SHOW, etc.)
    if any(sql_upper.startswith(x) for x in ["SHOW ", "DESC ", "DESCRIBE ", "EXPLAIN "]):
        return True

    # 2. Simple count/boundary probes (no JOIN, no GROUP BY)
    if "JOIN" not in sql_upper and "GROUP BY" not in sql_upper:
        # [V210.1] 目录/维表盘点豁免：纯目录/机构/字典表（药品目录、定点医药机构、行政区划）的盘点统计不属于算力探针
        is_catalog_query = any(tbl in sql_upper for tbl in ["FQZ_DRUG_MCS_INFO_LIST", "FQZ_ALL_YY_YD", "FQZ_ADMDVS"]) and not any(trx in sql_upper for trx in ["FQZ_GZ_JZSJ", "FQZ_FYMX"])
        if is_catalog_query:
            return False

        if any(x in sql_upper for x in ["COUNT(*)", "COUNT (", "MIN(SETL_TIME)", "MAX(SETL_TIME)", "MIN (SETL_TIME)", "MAX (SETL_TIME)"]):
            if "WHERE" in sql_upper and any(term in sql_upper for term in ["LIKE", "IN (", "IN(", "AND", "OR", "MULTISEARCH", "=", ">", "<", "!=", ">=", "<=", "BETWEEN"]):
                return False
            return True
        if sql_upper.startswith("SELECT COUNT"):
            if "WHERE" in sql_upper and any(term in sql_upper for term in ["LIKE", "IN (", "IN(", "AND", "OR", "MULTISEARCH", "=", ">", "<", "!=", ">=", "<=", "BETWEEN"]):
                return False
            return True

    # 3. Dictionary/DISTINCT lookups (item names, drug codes, etc.)
    if "DISTINCT" in sql_upper and "JOIN" not in sql_upper:
        has_groupby = "GROUP BY" in sql_upper or "HAVING" in sql_upper
        is_distinct_aggregate = bool(re.search(r'count\s*\(\s*distinct', sql_upper))
        if not has_groupby and not is_distinct_aggregate:
            if any(x in sql_upper for x in ["HILIST_NAME", "HILIST_CODE", "OPRN_OPRT_NAME", "DISE_NAME", "MED_TYPE", "ADM_DEPT_NAME", "DSCG_DEPT_NAME", "CHFPDR_NAME"]):
                return True

    # 4. Short, no-JOIN queries without analytical constructs
    if "JOIN" not in sql_upper and "GROUP BY" not in sql_upper and len(sql) < 500:
        if not ("HAVING" in sql_upper or "WINDOW" in sql_upper or "OVER" in sql_upper or "WHERE " in sql_upper or "ORDER BY" in sql_upper):
            if "GEND" not in sql_upper:
                return True

    # 5. Simple LIMIT probes without JOIN/GROUP BY
    if "LIMIT " in sql_upper and "JOIN" not in sql_upper and "GROUP BY" not in sql_upper and len(sql) < 500:
        if "WHERE " not in sql_upper and "ORDER BY" not in sql_upper:
            return True

    return False
