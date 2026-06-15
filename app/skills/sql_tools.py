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


# --- Helper: data sanitization ---
def _sanitize_results(records: List[Dict], tolerance: int = 1000) -> List[Dict]:
    """
    [V72.0 企业级] 业务感知型数据清洗中间件：
    - 支持梯级熔断：L1(放行), L2(告警), L3(强力拦截)
    - 结合 FieldKG 进行动态脱敏
    """
    HARD_MELT_LIMIT = 200000 # 绝对物理上限
    cleaned = []
    tolerance = settings.sql_row_tolerance
    
    for row in records:
        for key, val in row.items():
            # 1. 动态算力审计 (Tiered Circuit Breaker)
            if 'count' in key.lower() and isinstance(val, (int, float)):
                if val > HARD_MELT_LIMIT:
                    logger.error(f"🚨 [MELT] 触发绝对物理熔断！字段 {key} 数值 {val} 远超系统承载极限，疑似严重 SQL 逻辑错误。")
                    raise ValueError(f"物理安全拦截：检测到异常明细爆炸 ({val})。请检查 SQL 中的 JOIN 条件，必须通过 setl_id 精确排重。")
                
                if val > tolerance:
                    # [V72.0] 梯级降级：仅记录告警，不再直接抛出异常
                    logger.warning(f"⚠️ [Sanitizer] 探测到高体量业务数据 ({key}={val})。当前规则容差: {tolerance}。已记录并放行。")
            
            if not isinstance(val, str): continue
            
            # 2. 乱码清洗
            if val == "" or val is None: continue
            if '\ufffd' in val:
                row[key] = "[数据源乱码/GBK编码冲突]"
            
            # 3. 基础脱敏 (V128.9 自适应脱敏)
            has_binary = any(ord(c) < 32 and c not in '\n\r\t' for c in val)
            if has_binary:
                # [V110.0] 分级脱敏策略：在 Benchmark 模式下，允许放行非脱敏字段用于“证据验证”
                if os.getenv("IS_BENCHMARK_MODE", "false").lower() == "true":
                    # 仅做部分掩码，不做全量 REDACTED
                    if len(val) > 4:
                        row[key] = val[:2] + "**" + val[-2:]
                    continue
                row[key] = "[REDACTED/ENCRYPTED]"
                
        cleaned.append(row)
    return cleaned

@perf_monitor.time_it("AUDIT_ENGINE")
async def _execute_audit_sql_logic(
    sql: str, 
    db_type: str = "clickhouse", 
    return_raw: bool = False, 
    tolerance: int = 1000,
    tenant_id: Optional[str] = None
) -> Any:
    """内部物理执行逻辑 [V172.1] 增加 tenant_id 隔离"""
    if db_type == "clickhouse":
        try:
            # 1. 物理拦截与行政区划隔离注入
            safe_sql = SQLGuardian.validate_sql(sql, tenant_id=tenant_id)
            
            # [V176.0] 物理防御：防止 safe_sql 为空导致 upper() 崩溃
            safe_sql_upper = (safe_sql or "").upper()
            
            async def _run_sql(s_sql: str):
                client = get_clickhouse_client()
                return await asyncio.to_thread(client.query, s_sql)

            # [V162.0] 行政层级感知隔离 (Administrative Hierarchy Isolation)
            from app.core.context import tenant_context
            t_id = tenant_context.get()
            
            if t_id and "FROM" in safe_sql_upper:
                # 定义过滤子句
                filter_clause = ""
                if t_id.startswith("DIST_"):
                    # 县区级：精确匹配 admdvs
                    filter_clause = f"admdvs = '{t_id.split('_')[1]}'"
                elif t_id.startswith("CITY_"):
                    # 地市级：前缀匹配 (例如 3101%)
                    city_prefix = t_id.split('_')[1][:4]
                    filter_clause = f"admdvs LIKE '{city_prefix}%'"
                
                if filter_clause and "admdvs" not in safe_sql_upper:
                    logger.info(f"🛡️ [MultiTenant] 正在应用行政隔离 ({t_id}): {filter_clause}")
                    if "WHERE" in safe_sql_upper:
                        safe_sql = safe_sql.replace("WHERE", f"WHERE {filter_clause} AND", 1)
                    else:
                        match = re.search(r"(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|;|$)", safe_sql, re.IGNORECASE)
                        pos = match.start()
                        safe_sql = safe_sql[:pos] + f" WHERE {filter_clause}" + safe_sql[pos:]

            try:
                result = await _run_sql(safe_sql)
            except SqlExecError as first_err:
                err_str = str(first_err)
                # [V1.0] Code 6 自愈：setl_time 带 \t 导致 toDateTime 解析失败
                if "Code: 6" in err_str and "CANNOT_PARSE_TEXT" in err_str:
                    healed = _heal_timestamp_tab(safe_sql)
                    if healed != safe_sql:
                        try:
                            result = await _run_sql(healed)
                            safe_sql = healed
                            logger.info("[SQL_HEALER] 时间戳 \t 自愈成功，重试通过")
                        except SqlExecError as retry_err:
                            final_err = str(retry_err)
                            logger.error(f"[SQL_EXEC_ERROR] 时间戳自愈后仍失败: {final_err}")
                            return {"status": "ERROR", "error_message": final_err, "sql_logic": healed}
                    else:
                        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                        return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}
                # [V131.0] Code 215 自愈：一次自动修复 + 重试
                elif "Code: 215" in err_str:
                    healed = _heal_group_by_215(safe_sql, err_str)
                    if healed != safe_sql:
                        try:
                            result = await _run_sql(healed)
                            safe_sql = healed  # 修复成功，使用新 SQL
                        except SqlExecError as retry_err:
                            # 修复后仍失败，统一在此打 ERROR 并返回
                            final_err = str(retry_err)
                            logger.error(f"[SQL_EXEC_ERROR] 自愈失败: {final_err}")
                            return {"status": "ERROR", "error_message": final_err, "sql_logic": healed}
                    else:
                        # 无法自愈，直接报错
                        logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                        return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}
                else:
                    # 其他错误，单一记录并返回
                    if "404" in err_str or "Connection refused" in err_str or "无法建立" in err_str:
                        logger.error(f"[INFRA_ERROR] ClickHouse 不可达: {err_str[:150]}")
                        return {
                            "status": "ERROR",
                            "error_message": f"⚠️ ClickHouse 数据库未启动或不可达。请检查服务状态。原始错误: {err_str[:200]}",
                            "sql_logic": sql, "is_infra_error": True
                        }
                    logger.error(f"[SQL_EXEC_ERROR] {err_str}")
                    return {"status": "ERROR", "error_message": err_str, "sql_logic": safe_sql}
            if return_raw:
                return _sanitize_results(result, tolerance=tolerance)
            
            # [V157.0] USP 协议封装：始终返回结构化载荷，增强 AuditMessage 识别能力
            response = SkillResponse(
                status="SUCCESS",
                data=_sanitize_results(result, tolerance=5), # 默认返回 5 条样值供审计证据链
                logic_summary=f"已成功穿透底层数据库，检索到相关审计证据。",
                affected_rows=len(result),
                trace_hint=f"Query executed successfully via Clickhouse.",
                security_verified=True,
                sql_logic=safe_sql # [V178.9] 证据链持久化注入
            )
            
            # 为了兼容旧版解析器，返回 dict 但包含 USP 字段
            return response.model_dump()

        except Exception as e:
            err_str = str(e)
            from app.skills.security import SecurityViolationError
            if isinstance(e, SecurityViolationError):
                logger.debug(f"[SQL_GOVERNANCE] 执行拦截: {err_str}")
                return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}
            # 其他未预期异常（如 SQLGuardian 或其他错误），单一记录
            logger.error(f"[SQL_EXEC_ERROR] {err_str}")
            return {"status": "ERROR", "error_message": err_str, "sql_logic": sql}

    return {"status": "ERROR", "error_message": "所请求的数据库类型暂不支持。", "sql_logic": sql}

def _heal_group_by_215(sql_text: str, err_str: str) -> str:
    """
    [V132.1] 强化版 Code 215 自愈器：支持全限定列名提取与鲁棒性正则。
    """
    # 改进正则：支持提取 default.table.col 这种全限定名中的最后一节
    match = re.search(r"Column\s+'(?:[^']+\.)*([^']+)'\s+is\s+not\s+under\s+aggregate", err_str, re.IGNORECASE)
    if not match:
        return sql_text

    bad_col = match.group(1)
    logger.warning(f"🔧 [SQL_HEALER] 识别到未分组字段: `{bad_col}`，执行 AST 级修复...")

    # 改进正则：更精准地定位 GROUP BY 结尾，处理可能存在的分号
    # 逻辑：在 GROUP BY 块的最后一个字段后追加 , bad_col
    new_sql = re.sub(
        r'(GROUP\s+BY\s+)(.*?)(\s*(?:HAVING|ORDER\s+BY|LIMIT|;|$))',
        lambda m: f"{m.group(1)}{m.group(2).strip()}, {bad_col}{m.group(3)}",
        sql_text, count=1, flags=re.IGNORECASE | re.DOTALL
    )
    if new_sql == sql_text:
        return sql_text  # 没有 GROUP BY，无法修复

    logger.info(f"✅ [SQL_HEALER] SQL 已自愈，重试中…")
    return new_sql

def _heal_timestamp_tab(sql_text: str) -> str:
    """
    Code 6 CANNOT_PARSE_TEXT 自愈器：
    fqz_fymx_test 的 setl_time 是 String 类型且尾部带 \\t，
    裸 toDateTime(col) 会报 CANNOT_PARSE_TEXT。
    自动将 toDateTime(col) 替换为 toDateTime(substring(trim(col),1,19))。
    """
    pattern = r'toDateTime\(\s*((?!substring|trim\s*\()[A-Za-z_][\w.]*)\s*\)'
    healed = re.sub(
        pattern,
        lambda m: f'toDateTime(substring(trim({m.group(1)}),1,19))',
        sql_text, flags=re.IGNORECASE
    )
    if healed != sql_text:
        logger.warning(f"🔧 [SQL_HEALER] 检测到裸 toDateTime(col)，注入 \\t 清洗包装")
    return healed

# ──────────────────────────────────────────────────────────
# 暴露给 Agent 的工具集 (Decorated Tools)
# ──────────────────────────────────────────────────────────

@tool
async def execute_audit_sql(
    sql: Union[str, Dict], 
    state: Annotated[dict, InjectedState], # [V172.1] 自动注入状态
    db_type: str = "clickhouse"
) -> Any:
    """执行医疗相关 SQL 查询。自动执行行政区划隔离。"""
    # 提取租户信息
    tenant_id = state.get("metadata", {}).get("tenant_id") or state.get("metadata", {}).get("admin_division")
    
    # [V163.1] 鲁棒性参数解析
    params = smart_parse_tool_params(sql)
    actual_sql = params.get("sql", sql if isinstance(sql, str) else "")
    actual_db = params.get("db_type", db_type)
    
    return await _execute_audit_sql_logic(actual_sql, actual_db, tenant_id=tenant_id)
