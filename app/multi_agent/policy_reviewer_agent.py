from __future__ import annotations

import re
from typing import Any, Callable, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.multi_agent.contracts import ReviewVerdictArtifact, SQLAuditArtifact
from app.reporting.policy_matcher import match_policies
from app.skills.federated.law_rag_tools import query_law_database
from app.skills.rules.analysis_tools import expand_medical_codes, query_knowledge_base
from app.skills.schema.schema_tools import check_audit_governance

_REVIEWER_SYSTEM_PROMPT = """你是独立的医保政策法规与临床合理性复核专员 (PolicyReviewer)。
你的职责是打破初筛取证的“确认偏见”，站在客观医学与法定证据标准上对初筛结果进行独立质证：
1. 指出是否存在需要豁免剔除的临床合理适应症（如特殊肿瘤内分泌治疗、急抢救等），降低假阳性误报；
2. 结合法定依据评估整体风险等级（高 / 中 / 低），输出简明扼要的复核意见（不超过 200 字）。"""


def _resolve_statutory_citations(user_query: str) -> List[str]:
    """Resolve statutory citations from policy_matcher without hardcoding articles."""
    matched = match_policies(user_query)
    if not matched:
        return []
    if isinstance(matched, str):
        return [part.strip() for part in re.split(r"[；;]+", matched) if part.strip()]
    if isinstance(matched, list):
        citations: List[str] = []
        for item in matched:
            val = item.get("citation") or item.get("law") if isinstance(item, dict) else item
            text = str(val or "").strip()
            if text:
                citations.append(text)
        return citations
    return []


def _infer_risk_level(text: str, total_amt: float, total_rows: int) -> str:
    if "高" in text or total_amt >= 3000.0 or total_rows >= 50:
        return "高"
    if total_rows == 0 or "低" in text:
        return "低"
    return "中"


class PolicyReviewerSubagent:
    """剥离前序 SQL 推导过程、独立执行临床豁免降噪与法规对标的复核智能体。"""

    def __init__(self, llm_caller: Optional[Callable[..., Any]] = None):
        self._llm_caller = llm_caller

    def build_blind_review_messages(
        self,
        user_query: str,
        sql_artifacts: List[SQLAuditArtifact],
        citations: List[str],
    ) -> List[BaseMessage]:
        digest_lines = [
            f"- 专项 [{a.focus_title}]: 检出 {a.row_count} 条记录，涉及金额 ¥{a.total_amount:,.2f}，样本摘要: {a.raw_data[:200]}"
            for a in sql_artifacts
        ]
        citation_text = "; ".join(citations) if citations else "请参考 configs/policy_registry.yaml"
        user_brief = (
            f"【原始审计命题】：{user_query}\n"
            f"【客观取证摘要（已隐去前序推导过程）】：\n" + "\n".join(digest_lines) + "\n"
            f"【候选法规基准】：{citation_text}"
        )
        return [SystemMessage(content=_REVIEWER_SYSTEM_PROMPT), HumanMessage(content=user_brief)]

    async def _call_llm(self, messages: List[BaseMessage], config: Any) -> Any:
        if self._llm_caller is not None:
            return await self._llm_caller(role="auditor", messages=messages, config=config)
        from app.core.llm_provider import llm_provider

        return await llm_provider.chat(
            role="auditor",
            messages=messages,
            config=config,
            tools=[query_knowledge_base, query_law_database, expand_medical_codes, check_audit_governance],
            max_tokens=400,
        )

    async def review(
        self,
        user_query: str,
        sql_artifacts: List[SQLAuditArtifact],
        config: Any = None,
    ) -> ReviewVerdictArtifact:
        citations = _resolve_statutory_citations(user_query)
        total_rows = sum(a.row_count for a in sql_artifacts)
        total_amt = sum(a.total_amount for a in sql_artifacts)
        messages = self.build_blind_review_messages(user_query, sql_artifacts, citations)

        review_text = ""
        try:
            resp = await self._call_llm(messages, config)
            review_text = str(getattr(resp, "content", "") or "").strip()
        except Exception as exc:
            logger.warning(f"[PolicyReviewer] LLM 复核降级为静态法规匹配: {exc}")
            review_text = "建议结合参保人临床主副诊断病历进一步做适应症实质性复核，排除特殊病种合理用药后锁定违规。"

        risk = _infer_risk_level(review_text, total_amt, total_rows)
        citation_note = "; ".join(citations) if citations else "请参考 configs/policy_registry.yaml"
        return ReviewVerdictArtifact(
            exemption_notes=review_text,
            statutory_citations=citations,
            risk_level=risk,
            adjusted_summary=f"{review_text}\n适用法规依据：{citation_note}",
        )
