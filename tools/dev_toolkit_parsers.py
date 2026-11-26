"""
tools/dev_toolkit_parsers.py
============================
dev_toolkit CLI 子命令 argparse 解析器构建模块 (纯参数声明，无基础设施依赖)。
"""

import argparse


def _add_db_parsers(subparsers) -> argparse.ArgumentParser:
    db_parser = subparsers.add_parser("db", help="ClickHouse 数据库诊断与数据查询")
    db_sub = db_parser.add_subparsers(dest="action", help="数据库操作")
    db_sub.add_parser("health", help="检查 ClickHouse 健康状态")

    tables_p = db_sub.add_parser("tables", help="列出所有数据库表")
    tables_p.add_argument("--db", default="default", help="数据库名称 (默认 default)")

    desc_p = db_sub.add_parser("desc", help="查看表结构与字段类型")
    desc_p.add_argument("table", help="表名")
    desc_p.add_argument("--db", default="default", help="数据库名称")

    count_p = db_sub.add_parser("count", help="统计表数据行数")
    count_p.add_argument("table", help="表名")
    count_p.add_argument("--where", default=None, help="过滤条件")
    count_p.add_argument("--db", default="default", help="数据库名称")

    sample_p = db_sub.add_parser("sample", help="对表数据进行采样打印")
    sample_p.add_argument("table", help="表名")
    sample_p.add_argument("-n", "--limit", type=int, default=5, help="采样条数")
    sample_p.add_argument("--where", default=None, help="过滤条件")
    sample_p.add_argument("--cols", default=None, help="指定字段列表，英文逗号分隔")
    sample_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    sample_p.add_argument("--db", default="default", help="数据库名称")

    query_p = db_sub.add_parser("query", help="执行只读 SQL 查询")
    query_p.add_argument("sql", help="SQL 语句")
    query_p.add_argument("-n", "--limit", type=int, default=100, help="限制返回行数")
    query_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return db_parser


def _add_model_parsers(subparsers) -> argparse.ArgumentParser:
    model_parser = subparsers.add_parser("model", help="大模型提供商与算力池探活")
    model_sub = model_parser.add_subparsers(dest="action", help="模型操作")
    model_sub.add_parser("list", help="列出所有已配置的大模型")

    mtest_p = model_sub.add_parser("test", help="测试模型连通性与单轮推理")
    mtest_p.add_argument("model_id", help="模型 ID")
    mtest_p.add_argument("-p", "--prompt", default="请回复: OK", help="自定义测试 Prompt")

    mtool_p = model_sub.add_parser("test-tools", help="测试模型 Tool Calling 函数调用能力")
    mtool_p.add_argument("model_id", help="模型 ID")
    return model_parser


def _add_graph_parsers(subparsers) -> argparse.ArgumentParser:
    graph_parser = subparsers.add_parser("graph", help="Neo4j 知识图谱诊断")
    graph_sub = graph_parser.add_subparsers(dest="action", help="图数据库操作")
    graph_sub.add_parser("health", help="检查 Neo4j 连通性")
    graph_sub.add_parser("stats", help="统计图谱节点标签与关系类型")

    gquery_p = graph_sub.add_parser("query", help="执行 Cypher 查询")
    gquery_p.add_argument("cypher", help="Cypher 查询语句")
    gquery_p.add_argument("-n", "--limit", type=int, default=20, help="限制返回数量")
    return graph_parser


def _add_log_parsers(subparsers) -> argparse.ArgumentParser:
    log_parser = subparsers.add_parser("log", help="运行日志检索与报错定位")
    log_sub = log_parser.add_subparsers(dest="action", help="日志操作")

    lrec_p = log_sub.add_parser("recent", help="查看最新日志内容")
    lrec_p.add_argument("-n", "--lines", type=int, default=50, help="行数")

    lerr_p = log_sub.add_parser("errors", help="检索最近的 ERROR / 报错")
    lerr_p.add_argument("-k", "--keyword", default=None, help="关键字过滤")
    return log_parser
