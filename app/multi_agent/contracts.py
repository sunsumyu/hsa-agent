from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ExecutionTier(str, Enum):
    L0_FAST = "L0_FAST"
    L1_SOLO_SQL = "L1_SOLO_SQL"
    L2_MULTI_AGENT = "L2_MULTI_AGENT"


class SubTaskSpec(BaseModel):
    subtask_id: str
    focus_title: str
    query_instruction: str


class OrchestrationPlan(BaseModel):
    tier: ExecutionTier
    requires_graph: bool = False
    requires_policy_review: bool = False
    subtasks: List[SubTaskSpec] = Field(default_factory=list)
    reason: str = ""


class GraphClueArtifact(BaseModel):
    succeeded: bool
    degraded_to_relational: bool = False
    temp_table: Optional[str] = None
    entity_count: int = 0
    cypher_used: str = ""
    summary: str = ""


class SQLAuditArtifact(BaseModel):
    subtask_id: str
    focus_title: str
    sql_query: str = ""
    raw_data: str = ""
    row_count: int = 0
    total_amount: float = 0.0
    validated: bool = False
    error: Optional[str] = None
    retrieved_citations: List[Dict[str, Any]] = Field(default_factory=list)


class ReviewVerdictArtifact(BaseModel):
    exemption_notes: str = ""
    statutory_citations: List[str] = Field(default_factory=list)
    citations_ledger: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: Literal["高", "中", "低"] = "中"
    adjusted_summary: str = ""
