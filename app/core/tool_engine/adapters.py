"""
app/core/tool_engine/adapters.py
================================
[V200.0] 双适配器契约 (Protocol & Execution Adapters)。
符合 codebase-design 原则：
- 一个适配器是假接缝，两个适配器是真接缝 (ClickHouseAdapter + FakeDbAdapter; OpenAIToolAdapter + MCPToolAdapter)
- 接口是测试表面：FakeDbAdapter 使得上层代码与测试能够完全隔离物理网络与数据库。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel
from loguru import logger

from app.core.tool_engine.models import (
    ExecuteAuditSqlInput,
    AuditMedicalRuleInput,
    RunAnomalyDetectionInput,
    SubmitAuditPlanInput,
    ToolCallRequest,
    ToolResult,
)


# ─── 1. 物理执行适配器接缝 (Execution Adapter Seam) ──────────────────────────

class IDbExecutionAdapter(ABC):
    """底层数据执行器抽象接缝"""
    @abstractmethod
    async def query(self, sql: str) -> List[Dict[str, Any]]:
        pass


class ClickHouseAdapter(IDbExecutionAdapter):
    """真实 ClickHouse 物理数据库适配器"""
    async def query(self, sql: str) -> List[Dict[str, Any]]:
        from app.infra.db_conn import get_clickhouse_client
        client = get_clickhouse_client()
        return await asyncio.to_thread(client.query, sql)


class FakeDbAdapter(IDbExecutionAdapter):
    """
    内存测试适配器 (In-Memory Fake):
    允许所有单元测试在无 ClickHouse 实例的环境下瞬时运行，验证全部边界分支。
    """
    def __init__(self, mock_tables: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.mock_tables = mock_tables or {}
        self.query_history: List[str] = []

    def set_table_data(self, table_name: str, rows: List[Dict[str, Any]]):
        self.mock_tables[table_name.lower()] = rows

    async def query(self, sql: str) -> List[Dict[str, Any]]:
        self.query_history.append(sql)
        sql_lower = sql.lower()
        
        # 简单匹配表名并返回预置数据
        for tbl, rows in self.mock_tables.items():
            if tbl in sql_lower:
                return rows

        # 默认返回空或简单统计
        if "count" in sql_lower:
            return [{"total": len(self.mock_tables.get("default", []))}]
        return self.mock_tables.get("default", [])


# ─── 2. 大模型协议适配器接缝 (Protocol Adapter Seam) ──────────────────────────

class OpenAIToolAdapter:
    """将 Pydantic 工具入参模型转换为标准 OpenAI / LangChain Function Calling 规范"""
    @staticmethod
    def to_function_def(tool_name: str, description: str, pydantic_cls: Type[BaseModel]) -> Dict[str, Any]:
        schema = pydantic_cls.model_json_schema()
        # 清理不必要的元字段
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": schema
            }
        }


class MCPToolAdapter:
    """
    将工具转换为 Anthropic Model Context Protocol (MCP) 规范。
    支持暴露给外挂智能体、Artifact 看板或 IDE MCP 客户端。
    """
    @staticmethod
    def to_mcp_tool(tool_name: str, description: str, pydantic_cls: Type[BaseModel]) -> Dict[str, Any]:
        return {
            "name": tool_name,
            "description": description,
            "inputSchema": pydantic_cls.model_json_schema()
        }

    @staticmethod
    def parse_mcp_call(request_payload: Dict[str, Any]) -> ToolCallRequest:
        params = request_payload.get("params", {})
        return ToolCallRequest(
            call_id=str(request_payload.get("id", "mcp_call")),
            tool_name=params.get("name", ""),
            arguments=params.get("arguments", {})
        )
