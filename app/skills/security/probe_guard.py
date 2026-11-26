"""
app/skills/probe_guard.py
=========================
[Phase 3.4] SQL probe query detection.
"""

import re
from typing import List, Optional
from loguru import logger

STRUCTURAL_WHITELIST: List[str] = [
    "WITH ", "CASE WHEN", "UNION ALL", "UNION ", "OVER ", "OVER(",
    "COUNTIF(", "SUMIF(", "AVGIF(", "MAXIF(", "MINIF(", "IF(", "IF (",
]

AGGREGATE_WHITELIST: List[str] = [
    "QUANTILE", "PERCENTILE", "STDDEV", "VARIANCE", "MEDIAN", "CORR(", "QUANTILEEXACT",
]

_MACRO_DIM_TABLES = ("FQZ_CGZHAN_HOSP_FEE", "FQZ_DRUG_MCS_INFO_LIST", "FQZ_ALL_YY_YD", "FQZ_ADMDVS")
_CATALOG_TABLES = ("FQZ_DRUG_MCS_INFO_LIST", "FQZ_ALL_YY_YD", "FQZ_ADMDVS")
_TRX_TABLES = ("FQZ_GZ_JZSJ", "FQZ_FYMX")
_BUSINESS_WHERE_TERMS = (
    "LIKE", "IN (", "IN(", "AND", "OR", "MULTISEARCH", ">", "<", "=", "!=", ">=", "<=", "BETWEEN"
)
_BASELINE_PATTERNS = (
    r"SELECT\s+QUANTILE\s*\([^)]+\)\s*\([^)]+\)",
    r"SELECT\s+AVG\s*\([^)]+\)",
    r"SELECT\s+MEDIAN\s*\([^)]+\)",
    r"SELECT\s+STDDEV\s*\([^)]+\)",
    r"SELECT\s+PERCENTILE\s*\([^)]+\)",
    r"SELECT\s+SUM\s*\([^)]+\)",
)
_DICT_PROBE_COLS = (
    "HILIST_NAME", "HILIST_CODE", "OPRN_OPRT_NAME", "DISE_NAME",
    "MED_TYPE", "ADM_DEPT_NAME", "DSCG_DEPT_NAME", "CHFPDR_NAME",
)


def _has_business_where_filter(sql_upper: str) -> bool:
    return "WHERE" in sql_upper and any(term in sql_upper for term in _BUSINESS_WHERE_TERMS)


def _is_macro_or_whitelisted(sql: str, sql_upper: str, has_group_by: bool) -> bool:
    if any(tbl in sql_upper for tbl in _MACRO_DIM_TABLES) and not any(trx in sql_upper for trx in _TRX_TABLES):
        logger.debug(f"[ProbeGuard] macro report / dimension catalog exemption: {sql[:80]}...")
        return True
    if any(kw in sql_upper for kw in STRUCTURAL_WHITELIST):
        logger.debug(f"[ProbeGuard] structural whitelist exemption: {sql[:80]}...")
        return True
    if has_group_by and any(kw in sql_upper for kw in AGGREGATE_WHITELIST):
        logger.debug(f"[ProbeGuard] aggregate whitelist with GROUP BY: {sql[:80]}...")
        return True
    return False


def _classify_statistical_baseline(
    sql: str, sql_upper: str, has_group_by: bool, has_join: bool
) -> Optional[bool]:
    if any(re.search(p, sql_upper) for p in _BASELINE_PATTERNS) and not has_group_by and not has_join:
        logger.debug(f"[ProbeGuard] pure baseline query detected: {sql[:80]}...")
        return True
    if "AVG(" in sql_upper or "SUM(" in sql_upper or "AVERAGE(" in sql_upper:
        if has_group_by or has_join or _has_business_where_filter(sql_upper):
            logger.debug(f"[ProbeGuard] aggregate query exempt: {sql[:80]}...")
            return False
        logger.debug(f"[ProbeGuard] pure avg/sum baseline: {sql[:80]}...")
        return True
    return None


def _is_simple_count_or_dict_probe(sql: str, sql_upper: str, has_group_by: bool, has_join: bool) -> bool:
    if not has_join and not has_group_by:
        is_catalog = any(tbl in sql_upper for tbl in _CATALOG_TABLES) and not any(trx in sql_upper for trx in _TRX_TABLES)
        if is_catalog:
            return False
        count_tokens = ("COUNT(*)", "COUNT (", "MIN(SETL_TIME)", "MAX(SETL_TIME)", "MIN (SETL_TIME)", "MAX (SETL_TIME)")
        if (any(x in sql_upper for x in count_tokens) or sql_upper.startswith("SELECT COUNT")) and not _has_business_where_filter(sql_upper):
            return True

    if "DISTINCT" in sql_upper and not has_join:
        has_agg = has_group_by or "HAVING" in sql_upper
        if not has_agg and not re.search(r"count\s*\(\s*distinct", sql_upper):
            if any(col in sql_upper for col in _DICT_PROBE_COLS):
                return True

    if not has_join and not has_group_by and len(sql) < 500:
        if "WHERE " not in sql_upper and "ORDER BY" not in sql_upper:
            if "LIMIT " in sql_upper:
                return True
            if not any(kw in sql_upper for kw in ("HAVING", "WINDOW", "OVER", "GEND")):
                return True
    return False


def is_probe_query(sql: str) -> bool:
    """Determine whether a SQL string is a metadata/probe query."""
    if not sql:
        return True
    sql_upper = sql.upper().strip()
    has_group_by = "GROUP BY" in sql_upper
    has_join = "JOIN" in sql_upper

    if _is_macro_or_whitelisted(sql, sql_upper, has_group_by):
        return False
    stat_verdict = _classify_statistical_baseline(sql, sql_upper, has_group_by, has_join)
    if stat_verdict is not None:
        return stat_verdict
    if any(sql_upper.startswith(x) for x in ("SHOW ", "DESC ", "DESCRIBE ", "EXPLAIN ")):
        return True
    return _is_simple_count_or_dict_probe(sql, sql_upper, has_group_by, has_join)
