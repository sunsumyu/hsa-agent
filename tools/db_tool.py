#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/db_tool.py
================
快捷数据库排查 CLI 工具（基于 tools/dev_toolkit.py）

使用示例:
  python tools/db_tool.py health
  python tools/db_tool.py tables
  python tools/db_tool.py desc yb_fymx
  python tools/db_tool.py count yb_fymx
  python tools/db_tool.py sample yb_fymx -n 5
  python tools/db_tool.py query "SELECT count(*) FROM default.yb_fymx"
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.dev_toolkit import (
    main, get_db_client, check_db_health, list_db_tables, 
    describe_db_table, count_db_table, sample_db_table, execute_sql
)

if __name__ == "__main__":
    # 自动补全 "db" 子命令
    sys.argv.insert(1, "db")
    main()
