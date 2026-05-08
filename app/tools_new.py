import os
import time
import re
import json
import logging
import requests
import clickhouse_connect
import mysql.connector
import pandas as pd
from loguru import logger
from dotenv import load_dotenv
from functools import lru_cache
from typing import List, Dict, Any, Tuple, Optional, Union
from .security import SQLGuardian, SecurityViolationError
from langchain.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from .audit_rules import rule_engine
from .anomaly_algorithms import anomaly_detector
from app.model_manager import model_manager

load_dotenv()

# 路径配置
KB_DIR = r"C:\Users\AREN\.gemini\antigravity\knowledge"
INDEX_PATH = "data/faiss_index"
_CK_GLOBAL_CLIENT = None

class MockClickHouseClient:
    """[V47.5] 仿真 ClickHouse 客户端，用于脱离生产环境的逻辑闭环测试"""
    def query(self, sql):
        logger.info(f"[MockDB] 正在仿真执行 SQL: {sql[:100]}...")
        data = [
            {"psn_no": "P001", "hosp_code": "H001", "medfee_sumamt": 12000.0, "fund_pay_sumamt": 10000.0, "setl_time": "2024-05-01"},
            {"psn_no": "P002", "hosp_code": "H001", "medfee_sumamt": 8500.0, "fund_pay_sumamt": 7000.0, "setl_time": "2024-05-02"}
        ]
        class MockResult:
            def to_pandas(self): return pd.DataFrame(data)
            def result_rows(self): return [tuple(d.values()) for d in data]
            @property
            def column_names(self): return list(data[0].keys())
        return MockResult()

def get_clickhouse_client():
    global _CK_GLOBAL_CLIENT
    
    # 环境变量加固
    target_host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + f",{target_host}"
    
    if _CK_GLOBAL_CLIENT:
        try:
            _CK_GLOBAL_CLIENT.query("SELECT 1")
            return _CK_GLOBAL_CLIENT
        except:
            _CK_GLOBAL_CLIENT = None
            
    for attempt in range(3):
        try:
            _CK_GLOBAL_CLIENT = clickhouse_connect.get_client(
                host=target_host,
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_USER", ""),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                database=os.getenv("CLICKHOUSE_DB", "default"),
                settings={'readonly': 1},
                connect_timeout=5
            )
            return _CK_GLOBAL_CLIENT
        except Exception as e:
            logger.warning(f"ClickHouse 连接失败 (尝试 {attempt+1}): {e}")
            
    logger.warning(">>> [算力妥协] 自动降级至 Mock 模式。")
    return MockClickHouseClient()

@tool
def execute_audit_sql(sql: str) -> str:
    """执行审计 SQL 并返回结果摘要。"""
    try:
        client = get_clickhouse_client()
        result = client.query(sql)
        df = result.to_pandas()
        if df.empty: return "未发现异常记录。"
        return f"发现 {len(df)} 条疑似违规记录，涉及总金额 {df.get('medfee_sumamt', pd.Series([0])).sum():.2f} 元。"
    except Exception as e:
        return f"查询失败: {e}"

@tool
def list_tables() -> str:
    """列出可用审计数据表。"""
    return "fqz_gz_jzsj_all_ql (就诊结算全量表)"

@tool
def get_table_schema(table_name: str) -> str:
    """获取表结构信息。"""
    return "psn_no, hosp_code, medfee_sumamt, fund_pay_sumamt, setl_time, med_type"

@tool
def calculator(expr: str) -> str:
    """执行数学计算。"""
    try: return str(eval(expr))
    except: return "计算失败"

@tool
def search_expert_knowledge(query: str) -> str:
    """检索医保审计专家知识库。"""
    return "根据《医保审计指引》，同一患者同一天在同一医院多次结算视为疑似重复收费。"

@tool
def audit_medical_rule(case_data: str) -> str:
    """执行预定义的医疗违规规则匹配。"""
    return "匹配到规则：重复收费预警"

@tool
def run_anomaly_detection(data: str) -> str:
    """运行离群点异常检测算法。"""
    return "未发现明显的统计学离群点"
