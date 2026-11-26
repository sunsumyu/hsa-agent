"""
app.core.state — 分层状态定义
===============================
将 LangGraph State 拆分为三层:
  1. WorkflowState   — 框架通用 (messages, retry, error)
  2. TaskArtifacts    — 任务中间态 (query, raw_data, report)
  3. AuditDomainContext — 领域专属 (methodology, audit_findings)

组合为最终的 AuditState 供 agent_graph 使用,
同时保持各层可独立测试和复用。
"""

from __future__ import annotations

import operator
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    TypedDict,
)

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ── 辅助 Reducer 函数 ─────────────────────────────────────────

def _default_message_reducer(left: List, right: List) -> List:
    """[V90.4] 企业级消息合并：委托给 message_sanitizer 的去重+压缩+净化 pipeline。"""
    from app.core.memory.message_sanitizer import trim_and_sanitize
    return trim_and_sanitize(left, right, max_total=40, keep_head=5, keep_tail=25)


def _merge_dict(left: Dict, right: Dict) -> Dict:
    new = (left or {}).copy()
    new.update(right or {})
    return new


def _merge_list(left: List, right: List) -> List:
    """列表追加合并 reducer，用于 messages 等需要全量保留的字段。"""
    return (left or []) + (right or [])


def _overwrite_list(left: List, right: List) -> List:
    """列表覆盖 reducer，用于 sql_history 等由 coder_agent 内部维护全量的字段。

    如果 right 非空，直接用 right 覆盖 left（coder_agent 内部已累加全量）。
    如果 right 为空，保留 left（避免循环间覆盖丢失）。
    """
    if right is not None and len(right) > 0:
        return right
    return left or []


def _merge_citations(left: List, right: List) -> List:
    """合并并按 citation_id 去重当前轮次检索到的溯源账本。"""
    from app.core.rag.citation_ledger import merge_citation_ledgers
    return merge_citation_ledgers(left, right)


# ── Layer 1: 框架通用状态 ──────────────────────────────────────

class WorkflowState(TypedDict, total=False):
    """任何 LangGraph Agent 都需要的通用字段。"""
    messages: Annotated[Sequence[BaseMessage], _default_message_reducer]
    session_id: str
    retry_count: int
    plan_retry_count: int
    sql_retry_count: int
    tool_step_count: int
    error_log: Optional[str]
    human_input: Optional[str]
    is_awaiting_human: bool
    loop_count: int
    next_step: str


# ── Layer 2: 任务中间态 ────────────────────────────────────────

class TaskArtifacts(TypedDict, total=False):
    """与 "执行某项数据任务" 相关的中间产物, 不依赖具体行业。"""
    tasks: List[str]
    sql_query: str
    sql_history: Annotated[List[str], _overwrite_list]
    raw_data: str
    evidence_row_count: int  # [证据对账] 证据通道中实际可解析的行数（与 raw_data Append-Only 同步累加）
    sql_validated: bool
    execution_trace: List[str]
    schema_hint: Optional[str]
    metadata: Annotated[Dict[str, Any], _merge_dict]
    retrieved_citations: Annotated[List[Dict[str, Any]], _merge_citations]


# ── Layer 3: 领域专属上下文 ────────────────────────────────────

class AuditFinding(BaseModel):
    violation_type: str = Field(description="认定的违规类型")
    evidence: str = Field(description="证据描述，必须包含核心数值")
    amount: float = Field(description="涉及金额")
    count: int = Field(description="涉及违规次数")
    policy_basis: str = Field(description="政策依据")


class AuditReport(BaseModel):
    summary: str = Field(description="任务总结")
    findings: List[AuditFinding] = Field(description="发现列表")
    total_amount: float = Field(description="总计金额")
    finding_count: int = Field(default=0, description="发现的记录总数")
    risk_level: str = Field(description="高/中/低")
    risk_scores: Dict[str, int] = Field(
        default_factory=lambda: {
            "取证清晰度": 80,
            "经济影响": 50,
            "再犯风险": 30,
            "政策复杂性": 40,
            "发现隐蔽性": 60,
        }
    )


class AuditFeedback(BaseModel):
    decision: str = Field(description="判定结果: PASS 或 REJECT")
    reason: str = Field(description="拒绝或通过的详细理由")
    corrective_action: Optional[str] = Field(
        default=None, description="如果拒绝，给出的具体修正指令"
    )


class AuditDomainContext(TypedDict, total=False):
    """医保稽核领域专属字段。切换领域时替换此类即可。"""
    audit_findings: List[AuditFinding]
    structured_report: Optional[AuditReport]
    audit_feedback: Optional[AuditFeedback]
    methodology: str
    temp_table: Optional[str]
    # [V227.0 SPEC-227] 多轮状态机解耦与长链上下文治理字段
    current_turn_query: Optional[str]
    accumulated_findings: Annotated[List[Dict[str, Any]], _overwrite_list]
    turn_type: Optional[str]
    audit_notes: Annotated[List[str], _overwrite_list]


# ── 组合: 最终 State ──────────────────────────────────────────

class AuditState(WorkflowState, TaskArtifacts, AuditDomainContext):
    """完整的医保稽核 Agent 状态, 由三层组合而成。"""
    pass


# ── 状态生命周期与清洗标准化导出 (Matt Pocock Deep Module) ─────────
from app.core.state_governance import (
    build_initial_audit_state,
    create_turn_reset_patch,
    filter_state_for_logging,
)

