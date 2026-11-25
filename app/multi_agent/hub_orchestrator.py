from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.messages import AIMessage
from app.core.sql_evidence_resolver import resolve_user_query
from app.multi_agent.contracts import OrchestrationPlan, ReviewVerdictArtifact, SQLAuditArtifact
from app.multi_agent.graph_detective_agent import GraphDetectiveSubagent
from app.multi_agent.policy_reviewer_agent import PolicyReviewerSubagent
from app.multi_agent.sql_auditor_agent import SQLAuditorSubagent
from app.multi_agent.tier_classifier import classify_execution_plan
from app.reporting.report_renderer import report_renderer


def _merge_sql_artifacts(artifacts: List[SQLAuditArtifact]) -> Dict[str, Any]:
    combined_rows: List[Dict[str, Any]] = []
    sql_list: List[str] = []
    for art in artifacts:
        if art.sql_query:
            sql_list.append(art.sql_query)
        for row in report_renderer.clean_and_parse_raw_data(art.raw_data):
            enriched = dict(row)
            enriched.setdefault("_audit_dimension", art.focus_title)
            combined_rows.append(enriched)
    return {
        "raw_data": json.dumps(combined_rows, ensure_ascii=False),
        "evidence_row_count": len(combined_rows),
        "sql_query": sql_list[-1] if sql_list else "",
        "sql_history": sql_list,
        "sql_validated": any(a.validated for a in artifacts),
    }


def _build_hub_summary_and_methodology(
    sql_artifacts: List[SQLAuditArtifact],
    verdict: Optional[ReviewVerdictArtifact],
    plan: OrchestrationPlan,
) -> Tuple[str, str]:
    total_amt = sum(a.total_amount for a in sql_artifacts)
    total_cnt = sum(a.row_count for a in sql_artifacts)
    dim_lines = [f"- **{a.focus_title}**：检出 {a.row_count} 笔，金额 ¥{a.total_amount:,.2f}" for a in sql_artifacts]
    review_block = f"\n\n### 临床与法规独立复核意见\n{verdict.adjusted_summary}" if verdict else ""
    summary_md = (
        f"## 异构多专家联合核查结果\n"
        f"本次协同取证共覆盖 {len(sql_artifacts)} 个专项维度，合计锁定记录 {total_cnt} 笔，涉案金额 ¥{total_amt:,.2f}：\n"
        + "\n".join(dim_lines)
        + review_block
    )
    methodology = f"L2 多专家协同（{plan.reason}）"
    if verdict and verdict.statutory_citations:
        methodology += f" | 法规依据：{'; '.join(verdict.statutory_citations)}"
    return summary_md, methodology


class MultiAgentHubOrchestrator:
    """L2 异构多专家协同中枢：按计划串联图谱侦查、并发数仓核算与独立法规质证。"""

    def __init__(
        self,
        graph_agent: Optional[GraphDetectiveSubagent] = None,
        sql_agent: Optional[SQLAuditorSubagent] = None,
        policy_agent: Optional[PolicyReviewerSubagent] = None,
    ):
        self._graph = graph_agent or GraphDetectiveSubagent()
        self._sql = sql_agent or SQLAuditorSubagent()
        self._policy = policy_agent or PolicyReviewerSubagent()

    async def execute_hub(self, state: Dict[str, Any], config: Any = None) -> Dict[str, Any]:
        user_q = resolve_user_query(state)
        session_id = str(state.get("session_id") or "default")
        plan = classify_execution_plan(user_q, state.get("metadata"))
        trace: List[str] = [f"L2_HUB_INIT:{plan.reason}"]

        graph_clue = None
        if plan.requires_graph:
            graph_clue = await self._graph.investigate(user_q, config=config)
            trace.append(f"GRAPH_DETECTIVE:succeeded={graph_clue.succeeded},temp={graph_clue.temp_table}")

        sql_artifacts = await self._sql.run_parallel(
            plan.subtasks,
            session_id=session_id,
            config=config,
            graph_clue=graph_clue,
        )
        trace.append(f"SQL_AUDITOR_POOL:completed={len(sql_artifacts)}")

        verdict = None
        if plan.requires_policy_review:
            verdict = await self._policy.review(user_q, sql_artifacts, config=config)
            trace.append(f"POLICY_REVIEWER:risk={verdict.risk_level}")

        merged = _merge_sql_artifacts(sql_artifacts)
        summary_md, methodology = _build_hub_summary_and_methodology(sql_artifacts, verdict, plan)

        return {
            **merged,
            "tasks": [st.focus_title for st in plan.subtasks],
            "methodology": methodology,
            "temp_table": graph_clue.temp_table if graph_clue else state.get("temp_table"),
            "error_log": None if merged["sql_validated"] else "L2_SQL_UNVALIDATED",
            "messages": [AIMessage(content=summary_md)],
            "execution_trace": trace,
        }


multi_agent_hub = MultiAgentHubOrchestrator()
