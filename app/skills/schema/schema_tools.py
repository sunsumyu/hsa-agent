"""
app/skills/schema_tools.py
==========================
[Phase 3.2] Schema lookup, governance, expert knowledge, and calculator tools.

Extracted from tools.py. These @tool functions help the Agent discover table
structures, check compliance rules, and search domain knowledge.
"""

import os
import re
import json
from typing import Dict, Any
from loguru import logger
from langchain_core.tools import tool

from app.infra.db_conn import get_clickhouse_client


# Table name validation regex (prevents SQL injection in get_table_schema)
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_SAFE_EXPR_RE = re.compile(r"^[\d\s\.\+\-\*\/\(\)\%]+$")


def list_tables() -> str:
    """列出当前医保审计数据库中所有可用的物理表及其业务说明。从 SchemaRegistry 读取，不再写死。"""
    from app.core.registry.schema_registry import schema_registry
    return schema_registry.get_tables_summary() or "⚠️ 未加载到表定义"

# 表名校验正则: 仅允许字母/数字/下划线, 防止 SQL 注入
import re as _re_tools
_TABLE_NAME_RE = _re_tools.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

@tool
def get_table_schema(table_name: str) -> str:
    """获取 ClickHouse 物理表的真实字段结构。优先从 SchemaRegistry 读取，未注册时才走 DESCRIBE。"""
    # 安全校验: 防止 SQL 注入。原代码直接拼接 {table_name} 到 SQL。
    if not table_name or not _TABLE_NAME_RE.match(table_name):
        return f"非法表名: {table_name!r} (仅允许 a-zA-Z0-9_)"

    from app.core.registry.schema_registry import schema_registry
    # 1. 优先走注册表 (零 DB 费用)
    entry = schema_registry.get_table(table_name)
    if entry:
        return "\n".join(
            f"{f['name']} ({f.get('type', 'String')}) - {f.get('desc', '')}"
            for f in entry.fields
        )
    # 2. 未注册才查数据库 (此时已经通过名称正则校验, 安全)
    try:
        client = get_clickhouse_client()
        result = client.query(f"DESCRIBE TABLE {table_name}")
        fields = [f"{row[0]} ({row[1]})" for row in result.result_rows]
        return "\n".join(fields) if fields else f"表 {table_name} 不存在"
    except Exception as e:
        return f"获取表结构失败: {e}"


@tool
def calculator(expr: str) -> str:
    """高精度数学计算器。仅支持数字和算术运算符 (+ - * / % **)，指数上限 ±64；拒绝名称、属性访问、函数调用等。防止 eval() 的子类逃逸攻击。"""
    from app.skills.safe_math_evaluator import is_safe_math_expr, safe_eval_math_expression
    if not expr or not is_safe_math_expr(expr):
        return f"非法表达式: {expr!r} (仅允许数字和 + - * / % ( ) ** ，其中 ** 指数上限 ±64)"
    try:
        result = safe_eval_math_expression(expr)
        return str(result)
    except ValueError as e:
        return f"计算失败: {e}"
    except Exception as e:
        return f"计算异常: {e}"


@tool
def check_audit_governance() -> Dict[str, Any]:
    """
    [V118.0] 获取审计治理与物理合规规则。
    当 Agent 不确定表名合法性、字段脱敏要求或 SQL 执行限制时，必须调用此工具。
    返回内容：禁用的幻觉表名单、合法表前缀、敏感字段清单、强制时间过滤要求等。
    """
    from app.core.registry.schema_registry import schema_registry
    return {
        "forbidden_tables": list(schema_registry.get_forbidden_table_names()),
        "valid_table_prefixes": schema_registry.get_valid_prefixes(),
        "sensitive_fields": list(schema_registry.get_sensitive_fields()),
        "main_table": schema_registry.get_main_table(),
        "default_time_filter": "setl_time >= '2024-01-01' (仅适用于结算主表 fqz_gz_jzsj_all_ql)",
        "performance_constraints": {
            "max_execution_time_sec": schema_registry.get_max_execution_time(),
            "max_memory_usage": schema_registry.get_max_memory_usage()
        },
        "instruction": "严禁使用上述 forbidden_tables。针对主表(fqz_gz_jzsj_all_ql)等超大表建议带上时间过滤。对于费用明细表(fqz_fymx_test)或其他字典表，若用户未明确限定时间，严禁擅自追加年份过滤，以免过滤掉合规数据。"
    }

@tool
def lookup_medical_schema(keywords: str = "", table_name: str = "") -> str:
    """
    [V118.1] 检索医疗数据库物理 Schema。
    根据业务关键词或表名（如 'fqz_fymx_test'、'重复收费'、'总金额'）查询对应的物理表字段、DDL 结构及审计合规禁区。
    写 SQL 前必须调用此工具以防止字段幻觉和物理拦截。
    """
    from app.skills.medical_schema import MedicalSchemaSkill
    skill = MedicalSchemaSkill()
    return skill._run(keywords=keywords, table_name=table_name)

# ──────────────────────────────────────────────────────────
# 规则引擎与专家知识 (M3 成果落地)
# ──────────────────────────────────────────────────────────

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医保审计专家知识库。从 configs/expert_knowledge.yaml 加载由主题索引的专家提示。"""
    from app.skills.expert_knowledge_retriever import search_expert_knowledge_hints
    return search_expert_knowledge_hints(query)

@tool
def expand_medical_codes(intent: str) -> str:
    """
    [V125.0] 业务深度增强：从知识库检索医疗编码建议 (ICD-10/ICD-9)。
    """
    from app.skills.expert_knowledge_retriever import resolve_medical_code_mapping
    return resolve_medical_code_mapping(intent)


# 向后兼容重导出：calculator 已在本模块上方定义（原 safe_math_and_expert_kb
# 模块已并入，_load_expert_kb 随旧实现一并移除）
