#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/model_tool.py
===================
快捷模型诊断与算力池探测 CLI 工具（基于 tools/dev_toolkit.py）

使用示例:
  python tools/model_tool.py list
  python tools/model_tool.py test deepseek-v3
  python tools/model_tool.py test-tools doubao-smart
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.dev_toolkit import (
    main, list_available_models, test_model_call, test_tool_calling
)

if __name__ == "__main__":
    sys.argv.insert(1, "model")
    main()
