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


import ast
import operator
from typing import Dict, Any

# 允许的操作符映射
_CALC_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

def _safe_eval(expr: str) -> float:
    """
    [V179.4] 安全的数学表达式求值器。
    只允许数字和基本算术运算符，禁止任何名称访问。
    """
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError:
        raise ValueError(f"非法表达式语法: {expr}")
    
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不允许的类型: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _CALC_ALLOWED_OPS:
                raise ValueError(f"不允许的操作符")
            return _CALC_ALLOWED_OPS[op_type](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _CALC_ALLOWED_OPS:
                raise ValueError(f"不允许的单目操作符")
            return _CALC_ALLOWED_OPS[op_type](_eval(node.operand))
        else:
            raise ValueError(f"不允许的表达式类型")
    
    return _eval(tree)


@tool
def calculator(expr: str) -> str:
    """高精度数学计算器。仅支持数字和算术运算符，拒绝名称、属性访问、函数调用等。防止 eval() 的子类逃逸攻击。"""
    if not expr or not _SAFE_EXPR_RE.match(expr):
        return f"非法表达式: {expr!r} (仅允许数字和 + - * / ( ) % )"
    try:
        result = _safe_eval(expr)
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
def lookup_medical_schema(keywords: str) -> str:
    """
    [V118.1] 检索医疗数据库物理 Schema。
    根据业务关键词（如'重复收费'、'总金额'）查询对应的物理表字段、DDL 结构及审计合规禁区。
    写 SQL 前必须调用此工具以防止字段幻觉和物理拦截。
    """
    from app.skills.medical_schema import MedicalSchemaSkill
    skill = MedicalSchemaSkill()
    return skill._run(keywords)

# ──────────────────────────────────────────────────────────
# 规则引擎与专家知识 (M3 成果落地)
# ──────────────────────────────────────────────────────────

# [重构 V90.0] 专家知识库: 从 SemanticRetriever 识别任务型别返回针对性提示
import os as _os_tools
_EXPERT_KB_PATH = _os_tools.path.join(
    _os_tools.path.dirname(__file__), "..", "configs", "expert_knowledge.yaml"
)
_EXPERT_KB_CACHE = None

def _load_expert_kb():
    global _EXPERT_KB_CACHE
    if _EXPERT_KB_CACHE is not None:
        return _EXPERT_KB_CACHE
    try:
        import yaml
        with open(_EXPERT_KB_PATH, "r", encoding="utf-8") as f:
            _EXPERT_KB_CACHE = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _EXPERT_KB_CACHE = {}
    except Exception as e:
        logger.warning(f"[ExpertKB] load failed: {e}")
        _EXPERT_KB_CACHE = {}
    return _EXPERT_KB_CACHE

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医保审计专家知识库。从 configs/expert_knowledge.yaml 加载由主题索引的专家提示。"""
    if not query:
        return "⚠️ 查询为空"

    kb = _load_expert_kb()
    topics = kb.get("topics", [])
    if not topics:
        return "⚠️ 专家知识库未配置 (configs/expert_knowledge.yaml)"

    q_lower = query.lower()
    matched = []
    for topic in topics:
        keywords = topic.get("keywords", [])
        if any(kw.lower() in q_lower for kw in keywords):
            matched.append(
                f"【{topic.get('title', '')}】{topic.get('hint', '')}"
            )

    if not matched:
        return f"未检索到与 '{query}' 匹配的专家知识。已收录主题: " + ", ".join(
            t.get("title", "") for t in topics
        )

@tool
def expand_medical_codes(intent: str) -> str:
    """
    [V125.0] 业务深度增强：从知识库检索医疗编码建议 (ICD-10/ICD-9)。
    """
    kb_path = "configs/audit_knowledge_base.json"
    try:
        import json
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f).get("medical_codes", {})
    except:
        return "⚠️ 知识库加载失败"
    
    q = intent.strip()
    matched = []
    for k, v in kb.items():
        if k in q or q in k:
            res = f"【{k}】专业编码映射建议：\n"
            if "icd10" in v:
                res += f"- ICD-10 (疾病): {v['icd10'][0]} 至 {v['icd10'][1]}\n"
            res += f"- 业务说明: {v.get('desc', '')}"
            matched.append(res)
    
    if not matched:
        return f"未找到与 '{intent}' 相关的专业分类。建议直接尝试 LIKE '%{intent}%'。"
    
    return "\n\n".join(matched)
