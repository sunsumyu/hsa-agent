import os
import re
import clickhouse_connect
import mysql.connector
from loguru import logger
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

# 知识库路径
KB_DIR = r"C:\Users\AREN\.gemini\antigravity\knowledge"

# ClickHouse 连接配置
def get_clickhouse_client():
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username="",
            password=""
        )
        return client
    except Exception as e:
        logger.error(f"ClickHouse 连接失败: {e}")
        return None

# MySQL 连接配置 (根据扫描结果)
def get_mysql_conn():
    try:
        conn = mysql.connector.connect(
            host="127.0.0.1",
            port=3308,
            user="root",
            password="62901990552",
            database="fylqz_platform_new"
        )
        return conn
    except Exception as e:
        logger.error(f"MySQL 连接失败: {e}")
        return None

# 预设人造医院名库，用于物理脱敏
FAKE_HOSP_NAMES = [
    "仁心第一人民医院", "康泰中医院", "德济综合医院", "曙光医疗中心", 
    "同舟妇幼保健院", "博爱社区卫生中心", "建国骨科医院", "和平博仁医院",
    "长青康复医院", "春晖五官科医院", "明德二院", "厚德互联网医院"
]

class HospitalObfuscator:
    """医院名称物理脱敏器：确保真实医院名在输出时被随机且唯一地替换。"""
    _mapping = {}
    _cursor = 0

    @classmethod
    def mask(cls, real_name: str) -> str:
        if not real_name or not isinstance(real_name, str):
            return real_name
        # 简单判别：必须包含"医院"、"中心"、"门诊"等词汇才视为需要脱敏的机构名
        if not any(kw in real_name for kw in ["医院", "中心", "医务", "卫生", "保健"]):
            return real_name
            
        if real_name not in cls._mapping:
            fake_name = FAKE_HOSP_NAMES[cls._cursor % len(FAKE_HOSP_NAMES)]
            cls._mapping[real_name] = fake_name
            cls._cursor += 1
        return cls._mapping[real_name]

obfuscator = HospitalObfuscator()

@tool
def execute_audit_sql(sql: str, db_type: str = "clickhouse") -> str:
    """
    执行医疗相关 SQL 查询。
    db_type 可选: 'clickhouse' (默认, 审计数据) 或 'mysql' (业务配置数据)。
    如果不确定表名/字段名，请先执行 list_tables 或 get_table_schema。
    """
    logger.info(f"Agent 请求执行 [{db_type}] SQL: {sql}")
    
    if not sql.strip().upper().startswith("SELECT"):
        return "错误: 仅允许执行 SELECT 查询操作。"

    # 限制返回结果
    if "LIMIT" not in sql.upper():
        sql = sql.strip(";") + " LIMIT 50"

    if db_type.lower() == "clickhouse":
        return _execute_clickhouse(sql)
    else:
        return _execute_mysql(sql)

def _execute_clickhouse(sql):
    client = get_clickhouse_client()
    if not client: return "错误: 无法连接至 ClickHouse。"
    try:
        result = client.query(sql)
        if not result.result_rows: return ">>> [系统提示] 无结果。"
        col_names = list(result.column_names)
        return _format_and_mask(col_names, result.result_rows)
    except Exception as e:
        error_msg = str(e)
        if "diag_name" in error_msg.lower():
            return f"SQL 执行失败: 字段 `diag_name` 不存在。提示: 物理表中诊断信息缺失。请调用 get_table_schema 确认可选字段。"
        return f"ClickHouse 执行失败: {error_msg}"

def _execute_mysql(sql):
    conn = get_mysql_conn()
    if not conn: return "错误: 无法连接至 MySQL。"
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows: return ">>> [系统提示] 无结果。"
        col_names = [desc[0] for desc in cursor.description]
        return _format_and_mask(col_names, rows)
    finally:
        conn.close()

def _format_and_mask(col_names, rows):
    mask_indices = [i for i, col in enumerate(col_names) if any(key in col.lower() for key in ["name", "hosp", "ins"])]
    output = ["查询结果:", " | ".join(col_names)]
    for row in rows:
        masked_row = list(row)
        for idx in mask_indices:
            if isinstance(masked_row[idx], str):
                masked_row[idx] = obfuscator.mask(masked_row[idx])
        output.append(" | ".join(map(str, masked_row)))
    return "\n".join(output)

@tool
def list_tables(category: str = "all") -> str:
    """
    列出可用表清单。category 可选: 'audit' (审计计算表), 'biz' (业务管理表), 'all'。
    """
    audit_tables = [
        "fqz_all_yy_yd_1: 医保结算汇总表 (settl_time, medfee_sumamt)",
        "fqz_ptzy_hosp: 住院明细表 (setl_rq, medfee_sumamt, ipt_days_hj)",
        "policy_kb: 内部政策库模拟表"
    ]
    biz_tables = [
        "t_sys_user: 系统用户表",
        "t_task: 稽查任务表",
        "t_user_mapping: 用户映射表"
    ]
    
    res = []
    if category in ["audit", "all"]:
        res.append("--- [Audit ClickHouse] ---")
        res.extend(audit_tables)
    if category in ["biz", "all"]:
        res.append("--- [Business MySQL] ---")
        res.extend(biz_tables)
    
    return "\n".join(res) + "\n\n提示: 请使用 get_table_schema(table_name) 获取详细字段。"

@tool
def get_table_schema(table_name: str) -> str:
    """
    获取指定表的详细字段定义和架构信息。
    """
    # 优先在 ClickHouse 知识库中寻找
    for db in ["clickhouse", "mysql"]:
        file_path = os.path.join(KB_DIR, f"db_schema_{db}.md")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # 简单正则表达式匹配表结构部分
                pattern = rf"## 表: `{table_name}`\s+(.*?)\s+---"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return f"[{db.upper()} 表结构] {table_name}:\n{match.group(1).strip()}"
    
    return f"未找到表 `{table_name}` 的详细结构信息。请检查表名是否正确。"
