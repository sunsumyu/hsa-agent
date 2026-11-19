"""
app/skills/sql_tools.py
=======================
[Phase 3.2] SQL execution engine, sanitization, and auto-healing.

Extracted from tools.py. These functions form the core ClickHouse execution
pipeline used by execute_audit_sql and downstream rule/anomaly tools.
"""

import os
import re
import asyncio
from typing import List, Dict, Any, Union, Optional, Annotated
from loguru import logger
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.infra.db_conn import get_clickhouse_client, SqlExecError
from app.skills.security import SQLGuardian, SecurityViolationError
from app.api.perf_monitor import perf_monitor
from app.core.config import settings
from app.core.utils import smart_parse_tool_params
from app.core.registry.skill_protocol import SkillResponse


from app.skills.sql_execution_pipeline import execute_audit_sql_pipeline

# --- Helper: data sanitization ---
def _sanitize_results(records: List[Dict], tolerance: Optional[int] = None) -> List[Dict]:
    """[Backward Compatibility] 委托 sql_result_sanitizer 深模块"""
    from app.skills.sql_result_sanitizer import sanitize_sql_results
    return sanitize_sql_results(records, tolerance=tolerance)

async def _execute_audit_sql_logic(
    sql: str,
    db_type: str = "clickhouse",
    return_raw: bool = False,
    tolerance: int = 1000,
    tenant_id: Optional[str] = None,
    expected_table: Optional[str] = None
) -> Any:
    """[Backward Compatibility] 内部物理执行逻辑委托 sql_execution_pipeline 深模块"""
    return await execute_audit_sql_pipeline(
        sql=sql,
        db_type=db_type,
        return_raw=return_raw,
        tolerance=tolerance,
        tenant_id=tenant_id,
        expected_table=expected_table,
    )

def _heal_group_by_215(sql_text: str, err_str: str) -> str:
    """[兼容委托] 委托 clickhouse_error_healer 深模块"""
    from app.core.protocol.clickhouse_error_healer import heal_group_by_215
    return heal_group_by_215(sql_text, err_str)

def _heal_timestamp_tab(sql_text: str) -> str:
    """[兼容委托] 委托 clickhouse_error_healer 深模块"""
    from app.core.protocol.clickhouse_error_healer import heal_timestamp_tab
    return heal_timestamp_tab(sql_text)


# ──────────────────────────────────────────────────────────
# 暴露给 Agent 的工具集 (Decorated Tools)
# ──────────────────────────────────────────────────────────

@tool
async def execute_audit_sql(
    sql: Union[str, Dict],
    state: Annotated[dict, InjectedState], # [V172.1] 自动注入状态
    db_type: str = "clickhouse"
) -> Any:
    """执行医疗相关 SQL 查询。自动执行行政区划隔离和场景-表映射验证。"""
    # 提取租户信息和预期表
    metadata = state.get("metadata", {})
    tenant_id = metadata.get("tenant_id") or metadata.get("admin_division")
    expected_table = metadata.get("expected_table")  # [V173.0 NEW] 由 SceneTableSelector 提供

    # [V163.1] 鲁棒性参数解析
    params = smart_parse_tool_params(sql)
    actual_sql = params.get("sql", sql if isinstance(sql, str) else "")
    actual_db = params.get("db_type", db_type)

    return await _execute_audit_sql_logic(actual_sql, actual_db, tenant_id=tenant_id, expected_table=expected_table)
