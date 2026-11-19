#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/graph_tool.py
===================
快捷知识图谱诊断与 Cypher 查询 CLI 工具（基于 tools/dev_toolkit.py）

使用示例:
  python tools/graph_tool.py health
  python tools/graph_tool.py stats
  python tools/graph_tool.py query "MATCH (n) RETURN n LIMIT 10"
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.dev_toolkit import (
    main, check_graph_health, get_graph_stats, query_graph
)

if __name__ == "__main__":
    sys.argv.insert(1, "graph")
    main()
