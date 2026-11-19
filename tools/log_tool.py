#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/log_tool.py
=================
快捷日志排查与异常定位 CLI 工具（基于 tools/dev_toolkit.py）

使用示例:
  python tools/log_tool.py recent -n 50
  python tools/log_tool.py errors
  python tools/log_tool.py errors -k "timeout"
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.dev_toolkit import (
    main, get_recent_logs, search_log_errors
)

if __name__ == "__main__":
    sys.argv.insert(1, "log")
    main()
