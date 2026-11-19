from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from cores.state.base import BaseCognitiveState

class EvidenceItem(BaseModel):
    evidence_id: str
    title: str
    evidence_type: Literal["书证", "电子数据", "视听资料", "证人证言", "当事人陈述"]
    content_summary: str
    proof_date: Optional[str] = None
    amount: Optional[float] = None
    authenticity_level: Literal["高", "中", "存疑"] = "存疑"
    submission_status: Literal["已提交原件/核验", "仅口头陈述提及（待提交）", "缺失/待补充"] = "仅口头陈述提及（待提交）"

class CaseFact(BaseModel):
    fact_id: str
    narrative: str
    fact_time: Optional[str] = None
    evidence_anchors: List[str] = Field(default_factory=list)
    is_disputed: bool = False

class SyllogismSlice(BaseModel):
    element_id: str
    element_name: str
    statute_basis: str
    is_satisfied: bool
    supporting_facts: List[str] = Field(default_factory=list)
    vulnerability_notes: Optional[str] = None

class DisputeFocus(BaseModel):
    focus_id: str
    issue_statement: str
    cause_of_action: str
    governing_statutes: List[str] = Field(default_factory=list)
    elements: List[SyllogismSlice] = Field(default_factory=list)
    adjudication_tendency: str
    confidence_score: float = 0.5

class DialecticTurn(BaseModel):
    turn_index: int
    target_focus_id: str
    plaintiff_stance: str
    defendant_defense: str
    counter_strategy: str
    required_evidence_patch: List[str] = Field(default_factory=list)

class LegalCaseState(BaseCognitiveState):
    case_facts: List[CaseFact]
    evidence_items: List[EvidenceItem]
    dispute_foci: List[DisputeFocus]
    active_focus_id: Optional[str]
    dialectic_history: List[DialecticTurn]
    final_disposition: Optional[str]
    missing_evidence: List[str]
