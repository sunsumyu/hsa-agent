"""
app/skills/sql_execution_pipeline.py
====================================
ClickHouse 物理审计 SQL 执行管道（Deep Module）
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Dict, Optional, Tuple
from loguru import logger

from app.api.perf_monitor import perf_monitor
from app.core.registry.skill_protocol import SkillResponse
from app.infra.db_conn import SqlExecError
from app.skills.security import SQLGuardian, SecurityViolationError
from app.skills.sql.sql_result_sanitizer import inject_tenant_administrative_isolation, sanitize_sql_results


def _try_resolve_metadata_probe(sql: str, return_raw: bool) -> Optional[Any]:
    probe_match = re.match(
        r"^\s*(?:DESC|DESCRIBE(?:\s+TABLE)?|SHOW\s+COLUMNS\s+FROM)\s+([a-zA-Z0-9_\.]+)",
        (sql or "").strip(),
        re.IGNORECASE,
    )
    if not probe_match:
        return None
    target_raw = probe_match.group(1).split(".")[-1].strip("`\"' ")
    from app.core.registry.schema_registry import schema_registry

    entry = schema_registry.get_table(target_raw)
    if not entry:
        return None
    field_data = [
        {"column_name": f["name"], "data_type": f.get("type", "String"), "comment": f.get("desc", "")}
        for f in entry.fields
    ]
    logger.info(
        f"🔍 [DEEP_MODULE] 捕获元数据探针 `{sql.strip()}`，自动映射单一事实源返回结构 ({len(field_data)} 列)"
    )
    if return_raw:
        return field_data
    return SkillResponse(
        status="SUCCESS",
        data=field_data,
        logic_summary=f"已成功通过 Schema 注册表解析表 `{target_raw}` 的物理字段结构。",
        affected_rows=len(field_data),
        trace_hint="Table schema resolved via SchemaRegistry deep seam.",
        security_verified=True,
        sql_logic=sql,
    ).model_dump()


def _build_sql_error_payload(err_str: str, safe_sql: str, original_sql: str) -> Dict[str, Any]:
    if "404" in err_str or "Connection refused" in err_str or "无法建立" in err_str:
        logger.error(f"[INFRA_ERROR] ClickHouse 不可达: {err_str[:150]}")
        return {
            "status": "ERROR",
            "error_message": f"⚠️ ClickHouse 数据库未启动或不可达。请检查服务状态。原始错误: {err_str[:200]}",
            "sql_logic": original_sql,
            "is_infra_error": True,
        }
    logger.error(f"[SQL_EXEC_ERROR] {err_str}")
    return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}


async def _execute_with_clickhouse_healing(
    run_sql: Callable[[str], Any],
    safe_sql: str,
    original_sql: str,
) -> Tuple[Optional[Any], str, Optional[Dict[str, Any]]]:
    try:
        return await run_sql(safe_sql), safe_sql, None
    except SqlExecError as first_err:
        err_str = str(first_err)
        from app.core.protocol.clickhouse_error_healer import heal_clickhouse_execution_error

        healed = heal_clickhouse_execution_error(safe_sql, err_str)
        if not healed or healed == safe_sql:
            return None, safe_sql, _build_sql_error_payload(err_str, safe_sql, original_sql)
        try:
            res = await run_sql(healed)
            logger.info("[SQL_HEALER] 数据库异常自愈成功，重试通过")
            return res, healed, None
        except SqlExecError as retry_err:
            final_err = str(retry_err)
            logger.error(f"[SQL_EXEC_ERROR] 自愈重试后仍失败: {final_err}")
            return None, healed, {"status": "ERROR", "error_message": final_err, "sql_logic": healed}


def _format_sql_success_response(result: Any, safe_sql: str, return_raw: bool, tolerance: int) -> Any:
    if return_raw:
        return sanitize_sql_results(result, tolerance=tolerance)
    return SkillResponse(
        status="SUCCESS",
        data=sanitize_sql_results(result, tolerance=5),
        logic_summary="已成功穿透底层数据库，检索到相关审计证据。",
        affected_rows=len(result),
        trace_hint="Query executed successfully via Clickhouse.",
        security_verified=True,
        sql_logic=safe_sql,
    ).model_dump()


@perf_monitor.time_it("AUDIT_ENGINE")
async def execute_audit_sql_pipeline(
    sql: str,
    db_type: str = "clickhouse",
    return_raw: bool = False,
    tolerance: int = 1000,
    tenant_id: Optional[str] = None,
    expected_table: Optional[str] = None,
    client_getter: Optional[Callable[[], Any]] = None,
) -> Any:
    """内部物理执行逻辑 [V179.0] 增加 tenant_id 隔离 + expected_table 场景验证。"""
    if db_type.lower() != "clickhouse":
        return {"status": "ERROR", "error_message": "所请求的数据库类型暂不支持。", "sql_logic": sql}

    probe_res = _try_resolve_metadata_probe(sql, return_raw)
    if probe_res is not None:
        return probe_res

    try:
        from app.core.context import tenant_context
        from app.infra.db_conn import get_clickhouse_client

        validated_sql = SQLGuardian.validate_sql(sql, tenant_id=tenant_id, expected_table=expected_table)
        t_id = tenant_context.get() or tenant_id
        safe_sql = inject_tenant_administrative_isolation(validated_sql, t_id)

        async def _run_sql(s_sql: str) -> Any:
            client = client_getter() if client_getter is not None else get_clickhouse_client()
            return await asyncio.to_thread(client.query, s_sql)

        result, executed_sql, err_payload = await _execute_with_clickhouse_healing(_run_sql, safe_sql, sql)
        if err_payload is not None:
            return err_payload
        return _format_sql_success_response(result, executed_sql, return_raw, tolerance)
    except Exception as exc:
        err_str = str(exc)
        if isinstance(exc, SecurityViolationError):
            logger.debug(f"[SQL_GOVERNANCE] 执行拦截: {err_str}")
            return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
        return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
