"""
domains/hsa/state/case_state.py
===============================
HSA (Healthcare Security Administration) Audit Case State.
Domain-specific state contract for medical insurance compliance auditing.
"""

from typing import List, Dict, Any, Optional
from app.core.state import AuditState, WorkflowState, TaskArtifacts, AuditDomainContext

# Domain alias aligning with the generic cognitive architecture
HSAAuditState = AuditState

__all__ = [
    "HSAAuditState",
    "AuditState",
    "WorkflowState",
    "TaskArtifacts",
    "AuditDomainContext",
]
