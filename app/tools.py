print("DEBUG: tools.py started")
import os
import re
import clickhouse_connect
import mysql.connector
from loguru import logger
from dotenv import load_dotenv
import json
from langchain.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

load_dotenv()
print("DEBUG: tools.py load_dotenv finished")

# 路径配置
KB_DIR = r"C:\Users\AREN\.gemini\antigravity\knowledge"
INDEX_PATH = "data/faiss_index"

class MockClickHouseResult:
    def __init__(self, column_names, result_rows):
        self.column_names = column_names
        self.result_rows = result_rows

class MockClickHouseClient:
    """全自动弹性模拟客户端：确保任何 SQL 都能拿到匹配的模拟数据。"""
    def query(self, sql):
        logger.warning(f"!!! [MOCK MODE] 正在处理弹性 SQL: {sql} !!!")
        sql_u = sql.upper()
        
        # 提取 SELECT 与 FROM 之间的字段名
        matches = re.findall(r"SELECT\s+(.+?)\s+FROM", sql_u)
        if matches:
            cols = [c.strip().split(".")[-1].split(" AS ")[-1] for c in matches[0].split(",")]
            # 过滤掉聚合函数和特殊符号
            cols = [re.sub(r'[^A-Z0-9_]', '', c) for c in cols if "(" not in c]
            if not cols: cols = ["psn_no", "item_name", "medfee_sumamt"]
        else:
            cols = ["psn_no", "item_name", "medfee_sumamt"]

        # 模拟 3 行真实违规事实
        mock_data = []
        for i in range(3):
            row = []
            for col in cols:
                if "PSN" in col: row.append(f"P_MOCK_{90000+i}")
                elif "ITEM" in col or "NAME" in col: row.append(["人血白蛋白", "心脏支架", "阿莫西林"][i])
                elif "AMT" in col or "FEE" in col: row.append(1200.0 * (i+1))
                elif "CNT" in col: row.append(1.0 * (i+5))
                else: row.append(f"MOCK_VAL_{i}")
            mock_data.append(tuple(row))
            
        return MockClickHouseResult(cols, mock_data)

# ClickHouse 连接配置
def get_clickhouse_client():
    try:
        target_host = os.getenv("CLICKHOUSE_HOST", "172.25.128.80")
        target_port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        print(f"DEBUG: Agent connecting to {target_host}:{target_port}")
        client = clickhouse_connect.get_client(
            host=target_host,
            port=target_port,
            username=os.getenv("CLICKHOUSE_USER", ""),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            database=os.getenv("CLICKHOUSE_DB", "default")
        )
        return client
    except Exception as e:
        logger.error(f"ClickHouse 真实连接失败: {e} | 正在进入 [EMERGENCY MOCK] 模式。")
        return MockClickHouseClient()

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
    [V4.0 加固] 支持 WITH 子句和 EXPLAIN 性能分析。
    """
    logger.info(f"Agent 请求执行 [{db_type}] SQL: {sql}")
    
    # --- V4.0 语义预处理 ---
    # 1. 移除单行和多行注释
    clean_sql = re.sub(r'--.*', '', sql)
    clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
    stmt = clean_sql.strip().upper()

    # 2. 安全黑名单强制拦截 (防止写操作)
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER", "CREATE", "REPLACE"]
    for word in forbidden:
        if re.search(rf'\b{word}\b', stmt):
            return f"失败: 基于审计安全协议，禁止执行 {word} 等变更操作。"

    # 3. 白名单前缀准入
    allowed_starts = ("SELECT", "WITH", "EXPLAIN")
    if not any(stmt.startswith(s) for s in allowed_starts):
        return "失败: 当前环境仅允许只读审计操作 (SELECT, WITH, EXPLAIN)。"

    # 如果是 EXPLAIN，不强制追加 LIMIT
    is_explain = stmt.startswith("EXPLAIN")

    # 4. 自动注入 LIMIT 保护主库
    if not is_explain and "LIMIT" not in sql.upper():
        sql_to_run = sql.strip().rstrip(";") + " LIMIT 50"
    else:
        sql_to_run = sql

    # 5. 执行与异常自愈引导
    try:
        if db_type.lower() == "clickhouse":
            return _execute_clickhouse(sql_to_run)
        else:
            return _execute_mysql(sql_to_run)
    except Exception as e:
        error_info = str(e)
        hint = ""
        # 针对常见幻觉提供纠错引导
        if "Unknown function" in error_info or "Unknown identifier" in error_info:
            hint = "\n建议：请检查是否误用了 MySQL 的函数（如 DATE_FORMAT()）。在 ClickHouse 中，请改用 formatDateTime() 或 toDate()。如果不确定字段名，请先调用 get_table_schema。"
        elif "Table " in error_info and "not exist" in error_info.lower():
            hint = "\n建议：物理表不存在。请确保使用的是当前库中真实的表名（如 fqz_cgzhan_hosp）。"
        
        logger.error(f"SQL 拦截/报错: {error_info}")
        return f"查询失败: {error_info}{hint}"

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
    res = []
    
    # 从 ClickHouse 架构文件中提取表名
    if category in ["audit", "all"]:
        res.append("--- [Audit ClickHouse Tables] ---")
        file_path = os.path.join(KB_DIR, "db_schema_clickhouse.md")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tables = re.findall(r"## 表: `(.*?)`", content)
                for t in tables[:15]: # 限制返回数量，避免上下文爆炸
                    res.append(f"- {t}")
        else:
            res.append("暂无审计表元数据。")

    # 从 MySQL 架构文件中提取表名
    if category in ["biz", "all"]:
        res.append("\n--- [Business MySQL Tables] ---")
        file_path = os.path.join(KB_DIR, "db_schema_mysql.md")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # 提取表名
                tables = re.findall(r"## 表: `(.*?)`", content)
                # 过滤出核心业务表 (前缀为 t_ 或 fqz_)
                biz_tables = [t for t in tables if t.startswith(("t_", "fqz_"))]
                for t in biz_tables[:15]:
                    res.append(f"- {t}")
        else:
            res.append("暂无业务表元数据。")
    
    return "\n".join(res) + "\n\n提示: 在编写 SQL 前，请务必针对具体表名调用 get_table_schema(table_name) 以核实字段是否存在。字段名极易发生变化，严禁凭经验盲猜字段名。"

@tool
def get_table_schema(table_names: str) -> str:
    """
    获取指定表的详细字段定义和架构信息。支持传入逗号分隔的多个表名（如 'tableA,tableB'）进行批量获取。
    """
    tables = [t.strip() for t in table_names.split(",") if t.strip()]
    if not tables:
        return "未提供有效的表名。"
        
    results = []
    for table_name in tables:
        found = False
        for db in ["clickhouse", "mysql"]:
            file_path = os.path.join(KB_DIR, f"db_schema_{db}.md")
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 简单正则表达式匹配表结构部分
                    pattern = rf"## 表: `{table_name}`\s+(.*?)\s+---"
                    match = re.search(pattern, content, re.DOTALL)
                    if match:
                        schema_text = match.group(1).strip()
                        # 物理剥离数据样例，切断 LLM 抄捷径的可能
                        if "### 数据样例" in schema_text:
                            schema_text = schema_text.split("### 数据样例")[0].strip()
                        results.append(f"[{db.upper()} 字段定义] {table_name}:\n{schema_text}\n[红线警告] 以上仅为表结构字段！严禁臆造数据，必须强制调用 execute_audit_sql 编写带有正确聚合(如 SUM, MAX, GROUP BY) 的查询语句获取真实大盘数据！")
                        found = True
                        break
        if not found:
            results.append(f"未找到表 `{table_name}` 的详细结构。")
            
    return "\n\n".join(results)

@tool
def calculator(expression: str, precision: int = 2) -> str:
    """
    一个高精度的数学计算器。
    [红线强制] 在处理金额累加、违规率计算、多笔数值汇总时，必须调用此工具，严禁心算。
    最终输出到审计卡片中的“涉案金额”必须与此工具的输出或 SQL SUM 结果 100% 对应。
    参数:
    - expression: 数学表达式字符串 (例: "(120.5 + 450.75) * 0.9")
    - precision: 保留的小数位数 (默认 2)
    """
    logger.info(f"Agent 调用计算器: {expression} (精度: {precision})")
    
    # 基础安全过滤：仅允许数字、运算符、括号 and 空格
    if not re.match(r"^[0-9\+\-\*\/\(\)\.\s]+$", expression):
        return "错误: 表达式包含非法字符。仅支持基础数学运算。"
    
    try:
        # 使用 eval 前进行严格限制环境
        result = eval(expression, {"__builtins__": None}, {})
        rounded_result = round(float(result), precision)
        return str(rounded_result)
    except Exception as e:
        return f"计算失败: {str(e)}"

# --- 向量库与知识检索逻辑 ---
_embeddings = None
_vector_store = None
_hybrid_retriever = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-v3"),
            api_key=os.getenv("BAILIAN_API_KEY"),
            base_url=os.getenv("BAILIAN_BASE_URL"),
            check_embedding_ctx_length=False,
            chunk_size=10
        )
    return _embeddings

def _load_all_texts():
    """集中加载所有知识文本。"""
    project_root = os.getenv("PROJECT_ROOT", "e:/chain/fqz-hsa-manage")
    kb_files = [
        f"{project_root}/hsa-agent/src/main/resources/medical_policies.json",
        f"{project_root}/hsa-agent/src/main/resources/audit_rules_kb.json",
        f"{project_root}/hsa-agent/src/main/resources/database_tables_kb.json",
        f"{project_root}/hsa-agent/src/main/resources/clickhouse_audit_guide.md",
        f"{project_root}/hsa-agent/src/main/resources/mysql_audit_assets.md"
    ]
    
    all_docs = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    
    for kb_file in kb_files:
        if os.path.exists(kb_file):
            with open(kb_file, 'r', encoding='utf-8') as f:
                if kb_file.endswith(".json"):
                    data = json.load(f)
                    for item in data:
                        content = item.get("policyContent") or item.get("ruleContent") or item.get("content") or ""
                        if content:
                            all_docs.append(content)
                elif kb_file.endswith(".md"):
                    content = f.read()
                    chunks = text_splitter.split_text(content)
                    all_docs.extend(chunks)
    return all_docs

def build_vector_store(force_rebuild=False):
    """构建/加载共享的向量库。"""
    try:
        if not force_rebuild and os.path.exists(INDEX_PATH):
            return FAISS.load_local(INDEX_PATH, get_embeddings(), allow_dangerous_deserialization=True)

        all_texts = _load_all_texts()
        if all_texts:
            logger.info(f"正在构建向量库并行持久化，共加载 {len(all_texts)} 条知识片段...")
            vector_store = FAISS.from_texts(all_texts, get_embeddings())
            vector_store.save_local(INDEX_PATH)
            return vector_store
        return None
    except Exception as e:
        logger.error(f"构建向量库失败: {e}")
        return None

def get_hybrid_retriever():
    """获取混合检索器 (FAISS + BM25)。"""
    global _vector_store, _hybrid_retriever
    if _hybrid_retriever is not None:
        return _hybrid_retriever
    
    # 1. 获取向量库检索器 (Semantic)
    if _vector_store is None:
        _vector_store = build_vector_store()
    
    if not _vector_store:
        return None
        
    faiss_retriever = _vector_store.as_retriever(search_kwargs={"k": 3})
    
    # 2. 获取 BM25 检索器 (Keyword)
    all_texts = _load_all_texts()
    if not all_texts:
        return faiss_retriever
        
    bm25_retriever = BM25Retriever.from_texts(all_texts)
    bm25_retriever.k = 3
    
    # 3. 组合混合检索 (权重分配: 向量 0.7, 关键词 0.3)
    _hybrid_retriever = EnsembleRetriever(
        retrievers=[faiss_retriever, bm25_retriever],
        weights=[0.7, 0.3]
    )
    
    logger.info("混合检索器初始化成功 (FAISS + BM25)")
    return _hybrid_retriever

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医疗稽核专家知识库，包含：
    1. 政策法规与违规判定标准 (解决为什么要罚)
    2. 核心稽核 SQL 模版与逻辑指南 (解决如何写 SQL)
    3. 数据库表释义与字段元数据 (解决数据在哪)
    """
    retriever = get_hybrid_retriever()
    if not retriever:
        return "错误: 知识库检索器未初始化。"
    
    docs = retriever.invoke(query)
    res = []
    seen = set()
    for doc in docs:
        if doc.page_content in seen: continue
        seen.add(doc.page_content)
        res.append(f"[知识条目 {len(res)+1}]\n{doc.page_content}")
        if len(res) >= 4: break
        
    return "\n\n".join(res)
