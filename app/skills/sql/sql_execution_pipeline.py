"""
app/skills/sql_execution_pipeline.py
====================================
ClickHouse 物理审计 SQL 执行管道（Deep Module）

核心职责：
1. 元数据探针（DESCRIBE/SHOW COLUMNS）拦截与 SchemaRegistry 单一事实源接管
2. SQLGuardian 物理安全合规与场景-表映射验证
3. 行政层级感知隔离（Administrative Hierarchy Isolation）自动注入
4. 异步 ClickHouse 物理驱动执行
5. ClickHouse 语法与方言错误自动愈合（Healer）与重试
6. 基础设施不可达（连接中断/服务未启）精准识别与保护
7. 结果集安全脱敏熔断与 USP（Universal Skill Protocol）结构化协议封装
"""

from __future__ import annotations

import re
import asyncio
from typing import Any, Callable, Dict, List, Optional
from loguru import logger

from app.infra.db_conn import SqlExecError
from app.skills.security import SQLGuardian, SecurityViolationError
from app.api.perf_monitor import perf_monitor
from app.core.registry.skill_protocol import SkillResponse
from app.skills.sql.sql_result_sanitizer import sanitize_sql_results, inject_tenant_administrative_isolation


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
    """
    内部物理执行逻辑 [V179.0] 增加 tenant_id 隔离 + expected_table 场景验证。
    支持可选注入 client_getter，以便于离线单测与驱动替换。
    """
    if db_type.lower() != "clickhouse":
        return {"status": "ERROR", "error_message": "所请求的数据库类型暂不支持。", "sql_logic": sql}

    # 0. [Matt Pocock 深模块自愈] 元数据探针自动接管与自愈
    probe_match = re.match(
        r"^\s*(?:DESC|DESCRIBE(?:\s+TABLE)?|SHOW\s+COLUMNS\s+FROM)\s+([a-zA-Z0-9_\.]+)",
        (sql or "").strip(),
        re.IGNORECASE,
    )
    if probe_match:
        target_raw = probe_match.group(1).split(".")[-1].strip("`\"' ")
        from app.core.registry.schema_registry import schema_registry

        entry = schema_registry.get_table(target_raw)
        if entry:
            field_data = [
                {
                    "column_name": f["name"],
                    "data_type": f.get("type", "String"),
                    "comment": f.get("desc", ""),
                }
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

    try:
        # 1. 物理拦截与行政区划隔离注入 + 场景-表映射验证
        safe_sql = SQLGuardian.validate_sql(sql, tenant_id=tenant_id, expected_table=expected_table)

        # 客户端执行函数构建
        if client_getter is not None:
            def _get_client():
                return client_getter()
        else:
            from app.infra.db_conn import get_clickhouse_client
            def _get_client():
                return get_clickhouse_client()

        async def _run_sql(s_sql: str):
            client = _get_client()
            return await asyncio.to_thread(client.query, s_sql)

        # 2. 行政层级感知隔离 (Administrative Hierarchy Isolation)
        from app.core.context import tenant_context

        t_id = tenant_context.get() or tenant_id
        safe_sql = inject_tenant_administrative_isolation(safe_sql, t_id)

        # 3. 物理驱动执行与自愈重试
        try:
            result = await _run_sql(safe_sql)
        except SqlExecError as first_err:
            err_str = str(first_err)
            from app.core.protocol.clickhouse_error_healer import heal_clickhouse_execution_error

            healed = heal_clickhouse_execution_error(safe_sql, err_str)
            if healed and healed != safe_sql:
                try:
                    result = await _run_sql(healed)
                    safe_sql = healed
                    logger.info("[SQL_HEALER] 数据库异常自愈成功，重试通过")
                except SqlExecError as retry_err:
                    final_err = str(retry_err)
                    logger.error(f"[SQL_EXEC_ERROR] 自愈重试后仍失败: {final_err}")
                    return {"status": "ERROR", "error_message": final_err, "sql_logic": healed}
            else:
                if "404" in err_str or "Connection refused" in err_str or "无法建立" in err_str:
                    logger.error(f"[INFRA_ERROR] ClickHouse 不可达: {err_str[:150]}")
                    return {
                        "status": "ERROR",
                        "error_message": f"⚠️ ClickHouse 数据库未启动或不可达。请检查服务状态。原始错误: {err_str[:200]}",
                        "sql_logic": sql,
                        "is_infra_error": True,
                    }
                logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}

        # 4. 数据脱敏与结果组装
        if return_raw:
            return sanitize_sql_results(result, tolerance=tolerance)

        # 5. USP 协议封装：始终返回结构化载荷，增强 AuditMessage 识别能力
        response = SkillResponse(
            status="SUCCESS",
            data=sanitize_sql_results(result, tolerance=5),  # 默认返回 5 条样值供审计证据链
            logic_summary="已成功穿透底层数据库，检索到相关审计证据。",
            affected_rows=len(result),
            trace_hint="Query executed successfully via Clickhouse.",
            security_verified=True,
            sql_logic=safe_sql,  # 证据链持久化注入
        )

        return response.model_dump()

    except Exception as e:
        err_str = str(e)
        if isinstance(e, SecurityViolationError):
            logger.debug(f"[SQL_GOVERNANCE] 执行拦截: {err_str}")
            return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
        return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
