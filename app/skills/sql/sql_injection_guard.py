"""
[SPEC-227 / Matt Pocock Deep Module] SQL 物理注入与 NoSQL 语法防御深模块 (SQLInjectionGuard)

专职负责 SQL 输入非空检查、字面量规整、MongoDB/NoSQL 操作符注入拦截及堆叠查询分号防御。
"""

from __future__ import annotations
import re
from loguru import logger
from app.skills.security import SecurityViolationError


class SQLInjectionGuard:
    """输入清洗与物理防注入深模块"""

    MONGO_OPERATORS = (
        "$gte", "$lte", "$gt", "$lt", "$eq", "$ne",
        "$in", "$nin", "$or", "$and", "$regex"
    )

    @classmethod
    def clean_and_check_injection(cls, sql: str) -> str:
        """
        物理校验并清洗输入 SQL，拦截 NoSQL 操作符与堆叠查询。
        """
        if not sql:
            raise SecurityViolationError("SQL 内容不能为空")

        clean_sql = sql.strip()
        logger.info(f"🕵️ [SQLGuardian] 正在校验原始 SQL: {clean_sql[:300]}...")
        clean_sql = sql.replace('\\n', '\n').strip().rstrip(';； \n\r\t')

        # 1. Mongo / NoSQL 语法物理拦截：LLM 偶尔写出 {'$gte': ...} 当作 SQL 字面量
        for op in cls.MONGO_OPERATORS:
            if op in clean_sql:
                logger.error(f"[SECURITY] 检测到 MongoDB 操作符 {op} 混入 SQL")
                raise SecurityViolationError(
                    f"物理拦截：SQL 中混入了 MongoDB/NoSQL 操作符 `{op}`。"
                    f"ClickHouse SQL 不支持 `{{'$gte': '2024-01-01'}}` 这种语法，"
                    f"请改写为 `setl_time >= '2024-01-01'` 这种标准 SQL 比较语法。"
                )

        # 2. 堆叠查询物理检查：移除单双引号包裹的字面量后再检查分号，防止合法字符串内的分号被误报
        temp_sql = re.sub(r"'(?:''|[^'])*'", "", clean_sql)
        temp_sql = re.sub(r'"(?:""|[^"])*"', "", temp_sql)
        if ";" in temp_sql or "；" in temp_sql:
            logger.error(f"[SECURITY] 检测到非法堆叠查询攻击! [Raw]: {repr(sql)} | [Cleaned]: {repr(clean_sql)}")
            raise SecurityViolationError("物理拦截：检测到堆叠查询意图，系统已拒绝执行。")

        return clean_sql
