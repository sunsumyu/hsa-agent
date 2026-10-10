"""
app/core/tool_engine
====================
[V200.0] 统一工具协议执行引擎深度模块 (ToolEngine)

对外暴露简洁、不变的接缝表面：
- tool_engine: 单例引擎
- ToolEngine: 引擎类 (支持依赖注入)
- ToolCallRequest, ToolResult: 统一请求与不可变凭据
- FakeDbAdapter, ClickHouseAdapter: 物理与测试适配器
"""

from app.core.tool_engine.models import (
    ExecuteAuditSqlInput,
    AuditMedicalRuleInput,
    RunAnomalyDetectionInput,
    SubmitAuditPlanInput,
    ToolCallRequest,
    ToolResult,
)
from app.core.tool_engine.engine import ToolEngine, tool_engine
from app.core.tool_engine.grounder import SchemaGrounder
from app.core.tool_engine.adapters import (
    IDbExecutionAdapter,
    ClickHouseAdapter,
    FakeDbAdapter,
    OpenAIToolAdapter,
    MCPToolAdapter,
)

__all__ = [
    "tool_engine",
    "ToolEngine",
    "SchemaGrounder",
    "ToolCallRequest",
    "ToolResult",
    "ExecuteAuditSqlInput",
    "AuditMedicalRuleInput",
    "RunAnomalyDetectionInput",
    "SubmitAuditPlanInput",
    "IDbExecutionAdapter",
    "ClickHouseAdapter",
    "FakeDbAdapter",
    "OpenAIToolAdapter",
    "MCPToolAdapter",
]
