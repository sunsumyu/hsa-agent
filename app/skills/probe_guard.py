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

# Statistical analysis whitelist: SQL containing these keywords is legitimate
# business analysis and should NEVER be classified as a probe
ANALYSIS_WHITELIST: List[str] = [
    "QUANTILE",
    "PERCENTILE",
    "STDDEV",
    "VARIANCE",
    "MEDIAN",
    "CORR(",
    "WITH ",
    "CASE WHEN",
    "UNION ALL",
    "UNION ",
]


def is_probe_query(sql: str) -> bool:
    """
    Determine whether a SQL string is a metadata/probe query.

    Returns True for: SHOW/DESC/EXPLAIN, bare COUNT(*) without JOIN/GROUP BY,
    DISTINCT dictionary lookups, short no-JOIN queries without analytical clauses.

    Returns False for: empty (treated as probe at call sites), whitelisted
    statistical analysis, and any SQL with JOIN or complex analytical constructs.
    """
    if not sql:
        return True
    sql_upper = sql.upper().strip()

    # 0. Whitelist exemption: advanced analytical SQL is never a probe
    if any(kw in sql_upper for kw in ANALYSIS_WHITELIST):
        logger.debug(f"[ProbeGuard] whitelist exemption: {sql[:80]}...")
        return False

    # 1. Metadata probes (DESCRIBE, SHOW, etc.)
    if any(sql_upper.startswith(x) for x in ["SHOW ", "DESC ", "DESCRIBE ", "EXPLAIN "]):
        return True

    # 2. Simple count/boundary probes (no JOIN, no GROUP BY)
    if "JOIN" not in sql_upper and "GROUP BY" not in sql_upper:
        if any(x in sql_upper for x in ["COUNT(*)", "COUNT (", "MIN(SETL_TIME)", "MAX(SETL_TIME)", "MIN (SETL_TIME)", "MAX (SETL_TIME)"]):
            return True
        if sql_upper.startswith("SELECT COUNT"):
            return True

    # 3. Dictionary/DISTINCT lookups (item names, drug codes, etc.)
    if "DISTINCT" in sql_upper and "JOIN" not in sql_upper:
        if any(x in sql_upper for x in ["HILIST_NAME", "HILIST_CODE", "OPRN_OPRT_NAME", "DISE_NAME", "MED_TYPE", "ADM_DEPT_NAME", "DSCG_DEPT_NAME", "CHFPDR_NAME"]):
            return True

    # 4. Short, no-JOIN queries without analytical constructs
    if "JOIN" not in sql_upper and len(sql) < 500:
        if not ("HAVING" in sql_upper or "WINDOW" in sql_upper or "OVER" in sql_upper):
            if "GEND" not in sql_upper:
                return True

    # 5. Simple LIMIT probes without JOIN/GROUP BY
    if "LIMIT " in sql_upper and "JOIN" not in sql_upper and "GROUP BY" not in sql_upper and len(sql) < 500:
        return True

    return False
