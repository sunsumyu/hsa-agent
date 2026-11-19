"""
app/core/protocol/clickhouse_error_healer.py
============================================
[Deep Module] ClickHouse 运行期异常分类与自动自愈执行引擎

遵循 Matt Pocock 的 Deep Module 设计原则 (Narrow Interface, Deep Implementation):
- 窄接口:
    - heal_clickhouse_execution_error(sql: str, err_msg: str) -> Optional[str]
    - execute_with_auto_heal(query_func, initial_sql: str) -> Tuple[Any, str]
    - heal_group_by_215(sql_text: str, err_str: str) -> str
    - heal_timestamp_tab(sql_text: str) -> str
- 深实现:
    - 消化 Code: 6 (CANNOT_PARSE_TEXT，时间戳制表符污染) 正则清洗
    - 消化 Code: 215 (not under aggregate function) 全限定列名提取与 GROUP BY 动态补齐
    - 消化 Code: 184 (ILLEGAL_AGGREGATION / 聚合别名遮蔽物理列) AST 级重命名与限定
    - 封装通用异步重试执行闭环，消除业务调用方散落的 try-catch 重试样板代码
"""

from __future__ import annotations
import inspect
import re
from typing import Any, Callable, Optional, Tuple, TypeVar, Awaitable
from loguru import logger

T = TypeVar("T")


def heal_timestamp_tab(sql_text: str) -> str:
    """
    [Code: 6] 时间戳解析自愈器：
    1. fqz_fymx_test 的 setl_time 是 String 类型且尾部带 \\t，
       裸 toDateTime(col) 会报 CANNOT_PARSE_TEXT。
       自动将 toDateTime(col) 替换为 toDateTime(substring(trim(col),1,19))。
    2. 清洗形如 '2024-01-01\\t12:00:00' 中的 \\t 制表符。
    """
    if not sql_text:
        return ""

    cand = sql_text

    # 1. 自动注入 substring(trim(col), 1, 19) 清洗包装
    pattern = r'toDateTime\(\s*((?!substring|trim\s*\()[A-Za-z_][\w.]*)\s*\)'
    cand = re.sub(
        pattern,
        lambda m: f'toDateTime(substring(trim({m.group(1)}),1,19))',
        cand,
        flags=re.IGNORECASE
    )

    # 2. 替换日期时间字符串字面量中夹带的制表符为单个空格
    if "\t" in cand:
        cand = re.sub(
            r"('(?:\d{4}-\d{2}-\d{2})?)\t((?:\d{2}:\d{2}:\d{2})?')",
            r"\1 \2",
            cand
        )
        cand = re.sub(r"(toDateTime\s*\([^)]*)\t([^)]*\))", r"\1 \2", cand)
        cand = cand.replace("\t", " ")

    if cand != sql_text:
        logger.info("🔧 [ClickHouseHealer] Code: 6 时间戳已修复")
    return cand


def heal_group_by_215(sql_text: str, err_str: str) -> str:
    """
    [Code: 215] 聚合缺失列自愈器：
    从 ClickHouse 报错信息中提取未聚合字段，并追加到 GROUP BY 子句中。
    """
    match = re.search(
        r"Column\s+'(?:[^']+\.)*([^']+)'\s+is\s+not\s+under\s+aggregate",
        err_str,
        re.IGNORECASE
    )
    if not match:
        return sql_text

    bad_col = match.group(1).strip()
    logger.warning(f"🔧 [ClickHouseHealer] 识别到未分组字段: `{bad_col}`，执行追加修复...")

    new_sql = re.sub(
        r'(GROUP\s+BY\s+)(.*?)(\s*(?:HAVING|ORDER\s+BY|LIMIT|;|$))',
        lambda m: f"{m.group(1)}{m.group(2).strip()}, {bad_col}{m.group(3)}",
        sql_text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL
    )
    return new_sql


def heal_shadowing_alias_184(sql_text: str) -> str:
    """
    [Code: 184] 别名遮蔽物理列自愈器：
    当 WHERE 或 HAVING 中的过滤字段与 SELECT 别名同名时，解除遮蔽。
    """
    from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer
    return ClickHouseDialectHealer._fix_shadowing_aliases(sql_text)


def heal_clickhouse_execution_error(sql: str, err_msg: str) -> Optional[str]:
    """
    根据运行期 ClickHouse 错误特征，匹配最佳修复策略。
    若生成有效的新 SQL（且与原 SQL 不同），返回修复后的 SQL；否则返回 None。
    """
    if not sql or not err_msg:
        return None

    err_str = str(err_msg)

    # 1. Code 6: 时间戳解析错误
    if "Code: 6" in err_str or "CANNOT_PARSE_TEXT" in err_str or "\\t" in err_str or "\t" in sql:
        healed = heal_timestamp_tab(sql)
        if healed != sql:
            return healed

    # 2. Code 215: GROUP BY 缺失列
    if "Code: 215" in err_str or "not under aggregate" in err_str:
        healed = heal_group_by_215(sql, err_str)
        if healed != sql:
            return healed

    # 3. Code 184: 别名遮蔽物理列或非法聚合
    if (
        "Code: 184" in err_str
        or "ILLEGAL_AGGREGATION" in err_str
        or "is found in WHERE in query" in err_str
    ):
        healed = heal_shadowing_alias_184(sql)
        if healed != sql:
            return healed

    return None


async def execute_with_auto_heal(
    query_func: Callable[[str], Awaitable[T] | T],
    initial_sql: str
) -> Tuple[T, str]:
    """
    [高阶执行闭环] 封装【执行 -> 捕获 ClickHouse 异常 -> 自愈重写 -> 重试】完整生命周期。
    
    Args:
        query_func: 异步或同步查询函数，接收 SQL 字符串作为参数
        initial_sql: 待执行的原始或已净化 SQL
        
    Returns:
        Tuple[T, str]: (查询结果数据, 最终成功执行的 SQL)
        
    Raises:
        Exception: 若初次报错且无法自愈，或重试后仍报错，向上抛出最终异常
    """
    safe_sql = initial_sql
    try:
        res = query_func(safe_sql)
        records = await res if inspect.isawaitable(res) else res
        return records, safe_sql
    except Exception as first_err:
        err_str = str(first_err)
        healed_sql = heal_clickhouse_execution_error(safe_sql, err_str)

        if not healed_sql or healed_sql == safe_sql:
            # 无法自愈，直接抛出原始异常
            raise first_err

        logger.info(f"🔄 [ClickHouseHealer] 捕获执行异常，自动应用修复重试: {err_str[:120]}")
        try:
            res_retry = query_func(healed_sql)
            records = await res_retry if inspect.isawaitable(res_retry) else res_retry
            logger.info("✅ [ClickHouseHealer] 自愈重试成功执行通过！")
            return records, healed_sql
        except Exception as retry_err:
            logger.error(f"❌ [ClickHouseHealer] 自愈重试后仍失败: {retry_err}")
            raise retry_err
