"""
app.core — 与业务解耦的通用 Agent 框架层
"""
from app.core.state import WorkflowState, TaskArtifacts, AuditDomainContext
from app.core.prompt_registry import prompt_registry
from app.core.schema_registry import schema_registry
from app.core.rule_registry import rule_registry

__all__ = [
    "WorkflowState",
    "TaskArtifacts",
    "AuditDomainContext",
    "prompt_registry",
    "schema_registry",
    "rule_registry",
]
