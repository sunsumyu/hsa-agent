"""
domains/hsa/graph.py
====================
Healthcare Security Administration (HSA) Medical Insurance Audit Multi-Agent Graph.
Coordinates Aligner, Planner, Coder (SQLEXEC), Critic (Reflection), and Consolidator
agents with deterministic SQL AST and medical rule guardrails.
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from app.core.agent_graph import (
    build_graph as build_hsa_audit_graph,
    get_graph_executor,
    workflow as hsa_workflow,
    AgentGraph as HSAAgentGraph,
)
from domains.hsa.state.case_state import HSAAuditState


def get_hsa_executor(checkpointer=None, model_id: Optional[str] = None):
    """Obtain compiled LangGraph workflow executor for HSA audit."""
    return get_graph_executor(checkpointer=checkpointer, model_id=model_id)


__all__ = [
    "build_hsa_audit_graph",
    "get_hsa_executor",
    "hsa_workflow",
    "HSAAgentGraph",
    "HSAAuditState",
]
