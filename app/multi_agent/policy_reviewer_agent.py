from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from loguru import logger

from app.multi_agent.contracts import ReviewVerdictArtifact, SQLAuditArtifact
from app.reporting.policy_matcher import match_policies
from app.skills.federated.law_rag_tools import query_law_database
from app.skills.rules.analysis_tools import expand_medical_codes, query_knowledge_base
from app.skills.schema.schema_tools import check_audit_governance

_REVIEW_TOOLS = [query_knowledge_base, query_law_database, expand_medical_codes, check_audit_governance]
_STATIC_FALLBACK_REVIEW = "建议结合参保人临床主副诊断病历进一步做适应症实质性复核，排除特殊病种合理用药后锁定违规。"

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
    explicit = re.search(r"风险等级[：:\s]*【?\s*(高|中|低)", text or "")
    if explicit:
        return explicit.group(1)
    if total_amt >= 3000.0 or total_rows >= 50:
        return "高"
    if total_rows == 0:
        return "低"
    return "中"


async def _execute_review_tools(
    tool_calls: Sequence[Any],
    tools: Optional[Sequence[Any]] = None,
) -> List[ToolMessage]:
    tool_map = {getattr(t, "name", ""): t for t in (tools or _REVIEW_TOOLS)}
    messages: List[ToolMessage] = []
    for idx, tc in enumerate(tool_calls):
        is_dict = isinstance(tc, dict)
        name = tc.get("name", "") if is_dict else getattr(tc, "name", "")
        args = (tc.get("args") if is_dict else getattr(tc, "args", None)) or {}
        tc_id = (tc.get("id") if is_dict else getattr(tc, "id", None)) or f"call_{idx}"
        tool = tool_map.get(name)
        if tool is None:
            messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=str(tc_id)))
            continue
        try:
            res = await tool.ainvoke(args)
            messages.append(ToolMessage(content=str(res), tool_call_id=str(tc_id)))
        except Exception as exc:
            messages.append(ToolMessage(content=f"Tool error ({name}): {exc}", tool_call_id=str(tc_id)))
    return messages


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

    async def _call_llm(self, messages: List[BaseMessage], config: Any, allow_tools: bool = True) -> Any:
        if self._llm_caller is not None:
            chat_fn = self._llm_caller
        else:
            from app.core.llm_provider import llm_provider
            chat_fn = llm_provider.chat

        kwargs: Dict[str, Any] = {"role": "auditor", "messages": messages, "config": config, "max_tokens": 400}
        if allow_tools:
            kwargs["tools"] = _REVIEW_TOOLS
        return await chat_fn(**kwargs)

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
            resp = await self._call_llm(messages, config, allow_tools=True)
            tool_calls = getattr(resp, "tool_calls", None) or []
            if tool_calls:
                tool_msgs = await _execute_review_tools(tool_calls)
                resp = await self._call_llm([*messages, resp, *tool_msgs], config, allow_tools=False)
            review_text = str(getattr(resp, "content", "") or "").strip()
        except Exception as exc:
            logger.warning(f"[PolicyReviewer] LLM 复核降级为静态法规匹配: {exc}")

        if not review_text:
            review_text = _STATIC_FALLBACK_REVIEW

        risk = _infer_risk_level(review_text, total_amt, total_rows)
        citation_note = "; ".join(citations) if citations else "请参考 configs/policy_registry.yaml"
        return ReviewVerdictArtifact(
            exemption_notes=review_text,
            statutory_citations=citations,
            risk_level=risk,
            adjusted_summary=f"{review_text}\n适用法规依据：{citation_note}",
        )
