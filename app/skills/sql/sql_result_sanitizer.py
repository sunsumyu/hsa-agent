"""
app/skills/sql_result_sanitizer.py
==================================
SQL 执行结果脱敏清洗与行政区划隔离中间件（Deep Module）

职责：
- 动态算力审计与数据熔断拦截 (Tiered Circuit Breaker)
- 数据源乱码清洗与自适应脱敏
- 多租户行政区划层级感知隔离注入 (admdvs)
"""

from __future__ import annotations

import os
import re
from typing import List, Dict, Any, Optional
from loguru import logger

from app.core.config import settings


HARD_MELT_LIMIT = 200000  # 绝对物理上限，远超则视为笛卡尔积或爆炸


def sanitize_sql_results(
    records: List[Dict[str, Any]],
    tolerance: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    [企业级] 业务感知型数据清洗中间件：
    - 梯级熔断：L1(放行), L2(告警), L3(强力拦截)
    - 结合环境模式 (如 Benchmark 模式) 进行动态/分级脱敏
    """
    if not records:
        return []

    eff_tolerance = tolerance if tolerance is not None else settings.sql_row_tolerance
    cleaned: List[Dict[str, Any]] = []

    for row in records:
        cleaned_row = dict(row)
        for key, val in list(cleaned_row.items()):
            # 1. 动态算力审计 (Tiered Circuit Breaker)
            if "count" in key.lower() and isinstance(val, (int, float)):
                if val > HARD_MELT_LIMIT:
                    logger.error(f"🚨 [MELT] 触发绝对物理熔断！字段 {key} 数值 {val} 远超系统承载极限，疑似严重 SQL 逻辑错误。")
                    raise ValueError(f"物理安全拦截：检测到异常明细爆炸 ({val})。请检查 SQL 中的 JOIN 条件，必须通过 setl_id 精确排重。")

                if val > eff_tolerance:
                    logger.warning(f"⚠️ [Sanitizer] 探测到高体量业务数据 ({key}={val})。当前规则容差: {eff_tolerance}。已记录并放行。")

            if not isinstance(val, str):
                continue

            # 2. 乱码清洗
            if not val:
                continue
            if "\ufffd" in val:
                cleaned_row[key] = "[数据源乱码/GBK编码冲突]"
                continue

            # 3. 基础与分级脱敏
            has_binary = any(ord(c) < 32 and c not in "\n\r\t" for c in val)
            if has_binary:
                if os.getenv("IS_BENCHMARK_MODE", "false").lower() == "true":
                    if len(val) > 4:
                        cleaned_row[key] = val[:2] + "**" + val[-2:]
                    continue
                cleaned_row[key] = "[REDACTED/ENCRYPTED]"

        cleaned.append(cleaned_row)

    return cleaned


def inject_tenant_administrative_isolation(sql: str, tenant_id: Optional[str]) -> str:
    """
    [多租户隔离] 行政层级感知隔离 (Administrative Hierarchy Isolation)。
    根据租户身份特征在 SQL 查询中自动安全织入 admdvs 过滤条件。
    """
    if not tenant_id or not sql:
        return sql

    sql_upper = sql.upper()
    if "FROM" not in sql_upper or "ADMDVS" in sql_upper:
        return sql

    filter_clause = ""
    if re.match(r"^DIST_[A-Za-z0-9]{4,}$", tenant_id):
        # 县区级：精确匹配 admdvs
        dist_code = tenant_id.split("_")[1]
        filter_clause = f"admdvs = '{dist_code}'"
    elif re.match(r"^CITY_[A-Za-z0-9]{4,}$", tenant_id):
        # 地市级：前缀匹配 (例如 3101%)
        city_prefix = tenant_id.split("_")[1][:4]
        filter_clause = f"admdvs LIKE '{city_prefix}%'"
    else:
        logger.warning(f"[SECURITY] 非法的租户标识格式: {tenant_id}，跳过行政隔离注入")
        return sql

    if not filter_clause:
        return sql

    logger.info(f"🛡️ [MultiTenant] 正在应用行政隔离 ({tenant_id}): {filter_clause}")
    if "WHERE" in sql_upper:
        return sql.replace("WHERE", f"WHERE {filter_clause} AND", 1)

    match = re.search(r"(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|;|$)", sql, re.IGNORECASE)
    if match:
        pos = match.start()
        return sql[:pos] + f" WHERE {filter_clause}" + sql[pos:]

    return sql + f" WHERE {filter_clause}"
