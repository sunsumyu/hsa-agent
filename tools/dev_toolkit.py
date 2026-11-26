#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/dev_toolkit.py
====================
Argus-Agent 全局基础设施调试与数据诊断统一工具集 (Dev Toolkit)

【设计初衷】
在过去开发过程中，AI 助手在 scratch/ 目录下无脑编写了超过 500 个散落的一次性测试脚本（如 test_ck_*.py,
check_*.py, probe_*.py, explore_*.py）。本模块旨在将所有数据库探测、模型连通性排查、知识图谱诊断及
日志分析方法进行生产级收敛与统一封装，提供开箱即用的 CLI 命令行与 Python API。

【核心模块】
1. db:    ClickHouse / MySQL 连通性、表结构元数据、数据采样、行数统计与任意安全 SQL 执行。
2. model: 算力池大模型列表展示、端点探活、Prompt 调用与 Tool Calling（函数调用）能力验证。
3. graph: Neo4j 知识图谱连通性检测、节点与关系类型统计、Cypher 查询执行。
4. log:   运行日志检索、异常报错 (ERROR / Traceback) 快速定位。

【CLI 示例】
  python tools/dev_toolkit.py db health
  python tools/dev_toolkit.py db tables
  python tools/dev_toolkit.py db desc yb_fymx
  python tools/dev_toolkit.py db count yb_fymx
  python tools/dev_toolkit.py db sample yb_fymx -n 5
  python tools/dev_toolkit.py db query "SELECT count(*) FROM default.yb_fymx"
  python tools/dev_toolkit.py model list
  python tools/dev_toolkit.py model test deepseek-v3
  python tools/dev_toolkit.py model test-tools doubao-smart
  python tools/dev_toolkit.py graph health
  python tools/dev_toolkit.py graph stats
  python tools/dev_toolkit.py log recent -n 50
  python tools/dev_toolkit.py log errors
"""

import os
import sys
import json
import time
import argparse
from typing import Any, Dict, List, Optional

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger
from tools.dev_toolkit_parsers import (
    _add_db_parsers,
    _add_graph_parsers,
    _add_log_parsers,
    _add_model_parsers,
)


# ---------------------------------------------------------------------------
# 1. 数据库模块 (ClickHouse / MySQL)
# ---------------------------------------------------------------------------

def get_db_client():
    """获取标准 ClickHouse 客户端连接（带字符集自愈、代理穿透与协议自动回退）"""
    try:
        from app.infra.db_conn import get_clickhouse_client
        return get_clickhouse_client()
    except Exception as e:
        logger.error(f"[DB] 获取 ClickHouse 客户端失败: {e}")
        return None

def check_db_health() -> Dict[str, Any]:
    """检查 ClickHouse 数据库连通性、版本与延迟"""
    start = time.perf_counter()
    client = get_db_client()
    if not client:
        return {"status": "DOWN", "error": "无法建立连接，请确认服务已启动 (docker: clickhouse-server)"}
    try:
        res = client.query("SELECT version() as ver, currentDatabase() as db")
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        info = res[0] if res else {}
        return {
            "status": "UP",
            "latency_ms": latency_ms,
            "version": info.get("ver", "unknown"),
            "database": info.get("db", "default")
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

def list_db_tables(database: str = "default") -> List[Dict[str, Any]]:
    """列出指定数据库中的所有表及引擎信息"""
    client = get_db_client()
    if not client:
        raise RuntimeError("ClickHouse 未连接")
    sql = f"""
    SELECT name, engine, total_rows, total_bytes 
    FROM system.tables 
    WHERE database = '{database}' 
    ORDER BY name
    """
    try:
        return client.query(sql)
    except Exception:
        # 降级查询
        raw = client.query(f"SHOW TABLES FROM {database}")
        return [{"name": list(r.values())[0]} for r in raw]

def describe_db_table(table_name: str, database: str = "default") -> List[Dict[str, Any]]:
    """查询表字段元数据：字段名、数据类型、默认表达式、注释"""
    client = get_db_client()
    if not client:
        raise RuntimeError("ClickHouse 未连接")
    sql = f"""
    SELECT name, type, default_expression, comment 
    FROM system.columns 
    WHERE database = '{database}' AND table = '{table_name}'
    ORDER BY position
    """
    try:
        cols = client.query(sql)
        if cols:
            return cols
    except Exception as exc:
        logger.debug(f"[DB] system.columns 查询失败，降级 DESCRIBE TABLE: {exc}")
    # 降级使用 DESCRIBE TABLE
    return client.query(f"DESCRIBE TABLE {database}.{table_name}")

def count_db_table(table_name: str, where: Optional[str] = None, database: str = "default") -> int:
    """统计表总行数，支持自定义 WHERE 过滤条件"""
    client = get_db_client()
    if not client:
        raise RuntimeError("ClickHouse 未连接")
    sql = f"SELECT count(*) as cnt FROM {database}.{table_name}"
    if where:
        sql += f" WHERE {where}"
    res = client.query(sql)
    if res and len(res) > 0:
        return int(list(res[0].values())[0])
    return 0

def sample_db_table(
    table_name: str, 
    limit: int = 5, 
    columns: Optional[List[str]] = None, 
    where: Optional[str] = None,
    database: str = "default"
) -> List[Dict[str, Any]]:
    """对表进行数据采样，支持指定字段、过滤条件与条数"""
    client = get_db_client()
    if not client:
        raise RuntimeError("ClickHouse 未连接")
    cols_str = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols_str} FROM {database}.{table_name}"
    if where:
        sql += f" WHERE {where}"
    sql += f" LIMIT {limit}"
    return client.query(sql)

def execute_sql(sql: str, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
    """执行任意只读 SQL 查询，具有编码自动修复与行数保护"""
    client = get_db_client()
    if not client:
        raise RuntimeError("ClickHouse 未连接")
    clean_sql = sql.strip().rstrip(";")
    # 如果没有 LIMIT 且是 SELECT，默认加保护
    if limit and "limit" not in clean_sql.lower() and clean_sql.lower().startswith("select"):
        clean_sql += f" LIMIT {limit}"
    return client.query(clean_sql)


# ---------------------------------------------------------------------------
# 2. 模型与算力池模块 (LLM / Model Manager)
# ---------------------------------------------------------------------------

def list_available_models() -> List[Dict[str, Any]]:
    """列出当前系统注册的所有模型及提供商配置"""
    try:
        from app.infra.model_manager import model_manager
        results = []
        for model_id, config in model_manager.providers.items():
            results.append({
                "model_id": model_id,
                "provider": getattr(config, "provider", "unknown"),
                "context_window": getattr(config, "context_window", "unknown"),
                "max_tokens": getattr(config, "max_tokens", "unknown"),
                "supports_tools": getattr(config, "supports_tools", False)
            })
        return results
    except Exception as e:
        logger.error(f"[MODEL] 列出模型失败: {e}")
        return []

def test_model_call(model_id: str, prompt: str = "请回复: OK (系统链路正常)") -> Dict[str, Any]:
    """测试指定模型的连通性与单轮推理延迟"""
    start = time.perf_counter()
    try:
        from app.infra.model_manager import model_manager
        from langchain_core.messages import HumanMessage
        llm, _ = model_manager.get_adaptive_llm(model_id=model_id)
        resp = llm.invoke([HumanMessage(content=prompt)])
        latency = round((time.perf_counter() - start) * 1000, 2)
        content = resp.content if hasattr(resp, "content") else str(resp)
        return {
            "status": "SUCCESS",
            "model_id": model_id,
            "latency_ms": latency,
            "response": content.strip()[:200]
        }
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "FAILED",
            "model_id": model_id,
            "latency_ms": latency,
            "error": str(e)
        }

def test_tool_calling(model_id: str) -> Dict[str, Any]:
    """验证指定模型是否支持 LangChain / OpenAI 标准的工具调用 (Tool Call)"""
    start = time.perf_counter()
    try:
        from app.infra.model_manager import model_manager
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        @tool
        def query_medical_fee(hospital_name: str, year: int) -> str:
            """查询特定医院在特定年份的医保总费用"""
            return f"MockResult: {hospital_name} {year}年 发生费用 1,234,567.89元"

        llm, _ = model_manager.get_adaptive_llm(model_id=model_id)
        if not hasattr(llm, "bind_tools"):
            return {"status": "UNSUPPORTED", "model_id": model_id, "error": "模型客户端不支持 bind_tools 接口"}
        
        tool_bound_llm = llm.bind_tools([query_medical_fee])
        prompt = "帮我查询协和医院2024年的医保费用总额。"
        resp = tool_bound_llm.invoke([HumanMessage(content=prompt)])
        latency = round((time.perf_counter() - start) * 1000, 2)

        has_tool_calls = hasattr(resp, "tool_calls") and len(resp.tool_calls) > 0
        return {
            "status": "SUCCESS" if has_tool_calls else "NO_TOOL_CALL_TRIGGERED",
            "model_id": model_id,
            "latency_ms": latency,
            "tool_calls": getattr(resp, "tool_calls", []),
            "response_text": getattr(resp, "content", "")
        }
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ERROR", "model_id": model_id, "latency_ms": latency, "error": str(e)}


# ---------------------------------------------------------------------------
# 3. 知识图谱模块 (Neo4j)
# ---------------------------------------------------------------------------

def check_graph_health() -> Dict[str, Any]:
    """检查 Neo4j 图数据库连接状态与版本"""
    start = time.perf_counter()
    try:
        from app.infra.neo4j_manager import neo4j_manager
        driver = neo4j_manager.get_driver()
        with driver.session() as session:
            res = session.run("RETURN 1 as ping").single()
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "UP" if res and res["ping"] == 1 else "UNEXPECTED",
                "latency_ms": latency,
                "uri": os.getenv("NEO4J_URI", "unknown")
            }
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "DOWN", "latency_ms": latency, "error": str(e)}

def get_graph_stats() -> Dict[str, Any]:
    """统计 Neo4j 数据库中各类节点的标签和关系数量"""
    try:
        from app.infra.neo4j_manager import neo4j_manager
        driver = neo4j_manager.get_driver()
        with driver.session() as session:
            labels_res = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [r["label"] for r in labels_res]
            rel_res = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
            rel_types = [r["relationshipType"] for r in rel_res]
            return {
                "node_labels": labels,
                "node_label_count": len(labels),
                "relationship_types": rel_types,
                "relationship_type_count": len(rel_types)
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

def query_graph(cypher: str, limit: int = 20) -> List[Dict[str, Any]]:
    """执行只读 Cypher 图数据库查询"""
    from app.infra.neo4j_manager import neo4j_manager
    driver = neo4j_manager.get_driver()
    clean_cypher = cypher.strip().rstrip(";")
    if "limit" not in clean_cypher.lower() and clean_cypher.lower().startswith("match"):
        clean_cypher += f" LIMIT {limit}"
    with driver.session() as session:
        res = session.run(clean_cypher)
        return [dict(record) for record in res]


# ---------------------------------------------------------------------------
# 4. 日志分析模块 (Logs & Diagnostics)
# ---------------------------------------------------------------------------

def get_recent_logs(lines: int = 50, log_dir: str = "logs") -> List[str]:
    """读取指定日志目录下最新的运行日志行"""
    if not os.path.exists(log_dir):
        return [f"日志目录 {log_dir} 不存在"]
    log_files = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")]
    if not log_files:
        return [f"目录 {log_dir} 中未找到 .log 文件"]
    latest_file = max(log_files, key=os.path.getmtime)
    with open(latest_file, "r", encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()
        return all_lines[-lines:]

def search_log_errors(keyword: Optional[str] = None, max_results: int = 30, log_dir: str = "logs") -> List[str]:
    """在运行日志中快速检索 ERROR、CRITICAL 或包含指定关键字的异常行"""
    if not os.path.exists(log_dir):
        return []
    log_files = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")], key=os.path.getmtime, reverse=True)
    matches = []
    targets = ["error", "critical", "traceback", "exception"]
    if keyword:
        targets.append(keyword.lower())

    for fpath in log_files[:3]:  # 仅检查最近的 3 个日志文件
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                lower_line = line.lower()
                if any(t in lower_line for t in targets):
                    matches.append(f"[{os.path.basename(fpath)}:{line_no}] {line.strip()}")
                    if len(matches) >= max_results:
                        return matches
    return matches


# ---------------------------------------------------------------------------
# 5. 格式化输出辅助函数
# ---------------------------------------------------------------------------

def _print_json(data: Any):
    """友好打印 JSON 格式"""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))

def _print_table(rows: List[Dict[str, Any]], max_rows: int = 50):
    """以清晰的 ASCII 表格形式打印数据"""
    if not rows:
        print("（无结果）")
        return
    headers = list(rows[0].keys())
    # 计算列宽（最多截断50字符）
    col_widths = {h: min(max(len(str(h)), max(len(str(r.get(h, ""))) for r in rows[:max_rows])), 50) for h in headers}
    
    header_line = " | ".join(str(h).ljust(col_widths[h]) for h in headers)
    sep_line = "-+-".join("-" * col_widths[h] for h in headers)
    print(header_line)
    print(sep_line)
    for r in rows[:max_rows]:
        line = " | ".join(str(r.get(h, "")).replace("\n", " ").ljust(col_widths[h])[:col_widths[h]] for h in headers)
        print(line)
    if len(rows) > max_rows:
        print(f"... 仅展示前 {max_rows} 条数据，共 {len(rows)} 条")


# ---------------------------------------------------------------------------
# 6. CLI 命令行分发入口
# ---------------------------------------------------------------------------

def _print_rows(rows: List[Dict[str, Any]], as_json: bool) -> None:
    if as_json:
        _print_json(rows)
    else:
        _print_table(rows)


def _handle_db(args, parser) -> None:
    action = args.action
    if action == "health":
        _print_json(check_db_health())
    elif action == "tables":
        _print_table(list_db_tables(args.db))
    elif action == "desc":
        _print_table(describe_db_table(args.table, args.db))
    elif action == "count":
        cnt = count_db_table(args.table, args.where, args.db)
        print(f"表 [{args.db}.{args.table}] 符合条件的行数: {cnt}")
    elif action == "sample":
        cols = [c.strip() for c in args.cols.split(",")] if args.cols else None
        _print_rows(sample_db_table(args.table, args.limit, cols, args.where, args.db), args.json)
    elif action == "query":
        _print_rows(execute_sql(args.sql, args.limit), args.json)
    else:
        parser.print_help()


def _handle_model(args, parser) -> None:
    if args.action == "list":
        _print_table(list_available_models())
    elif args.action == "test":
        _print_json(test_model_call(args.model_id, args.prompt))
    elif args.action == "test-tools":
        _print_json(test_tool_calling(args.model_id))
    else:
        parser.print_help()


def _handle_graph(args, parser) -> None:
    if args.action == "health":
        _print_json(check_graph_health())
    elif args.action == "stats":
        _print_json(get_graph_stats())
    elif args.action == "query":
        _print_json(query_graph(args.cypher, args.limit))
    else:
        parser.print_help()


def _handle_log(args, parser) -> None:
    if args.action == "recent":
        for line in get_recent_logs(args.lines):
            print(line, end="")
    elif args.action == "errors":
        matches = search_log_errors(args.keyword)
        if not matches:
            print("近期日志中未发现明显报错。")
        for m in matches:
            print(m)
    else:
        parser.print_help()


def main():
    parser = argparse.ArgumentParser(
        prog="dev_toolkit",
        description="Argus-Agent 全局基础设施调试与数据诊断统一工具集"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="子功能模块")
    handlers = {
        "db": (_add_db_parsers(subparsers), _handle_db),
        "model": (_add_model_parsers(subparsers), _handle_model),
        "graph": (_add_graph_parsers(subparsers), _handle_graph),
        "log": (_add_log_parsers(subparsers), _handle_log),
    }

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        return
    sub_parser, handler = handlers[args.subcommand]
    handler(args, sub_parser)


if __name__ == "__main__":
    main()
