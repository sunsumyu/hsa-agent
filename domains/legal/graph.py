"""
domains/legal/graph.py
======================
民商事法律辩法多智能体编排图 (LangGraph)。
支持：
1. 真实 LLM 语义抽取、焦点三段论、红蓝攻防与法官心证（失败自动回退确定性规则）
2. 神经符号硬门禁 (LegalLogicGate)
3. 人工介入循环 (HITL): 当关键证据缺失或仅停留在口头陈述未核验时，主动 interrupt() 挂起等待用户补充证据或选择跳过继续
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from domains.legal.state.case_state import LegalCaseState
from domains.legal.agents.fact_extractor import FactExtractor
from domains.legal.agents.focus_planner import FocusPlanner
from domains.legal.agents.dialectic_arguer import DialecticArguer
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator
from domains.legal.gates.legal_logic_gate import LegalLogicGate


_SKIP_HINTS = ("跳过", "继续", "没有", "暂无", "不补", "直接评判", "按现有")


def _merge_usage(meta: Dict[str, Any], usage: Dict[str, Any]) -> Dict[str, Any]:
    if not usage:
        return meta
    prev = dict(meta.get("token_usage") or {"prompt": 0, "completion": 0, "model_id": "rule-fallback"})
    prev["prompt"] = int(prev.get("prompt", 0)) + int(usage.get("prompt", 0))
    prev["completion"] = int(prev.get("completion", 0)) + int(usage.get("completion", 0))
    if usage.get("model_id"):
        prev["model_id"] = usage["model_id"]
    new_meta = dict(meta)
    new_meta["token_usage"] = prev
    return new_meta


async def aligner_node(state: LegalCaseState):
    extractor = FactExtractor()
    meta = dict(state.get("metadata") or {})
    user_q = meta.get("user_question", "")
    facts, evidence, missing, usage = await extractor.aextract(user_q)
    meta = _merge_usage(meta, usage)
    return {
        "case_facts": facts,
        "evidence_items": evidence,
        "missing_evidence": missing,
        "metadata": meta,
        "current_step": "ALIGNER",
    }


async def planner_node(state: LegalCaseState):
    planner = FocusPlanner()
    meta = dict(state.get("metadata") or {})
    cause = meta.get("cause", "民间借贷纠纷")
    user_q = meta.get("user_question", "")
    foci, usage = await planner.aplan(cause, user_q)
    meta = _merge_usage(meta, usage)
    return {
        "dispute_foci": foci,
        "active_focus_id": foci[0].focus_id if foci else None,
        "metadata": meta,
        "current_step": "PLANNER",
    }


async def dialectic_node(state: LegalCaseState):
    arguer = DialecticArguer()
    meta = dict(state.get("metadata") or {})
    foci = state.get("dispute_foci", [])
    active_focus = foci[0] if foci else None
    user_q = meta.get("user_question", "")
    ev_items = state.get("evidence_items", [])
    ev_summary = "\n".join(
        f"- {e.title}: {e.submission_status} (效力: {e.authenticity_level})"
        for e in ev_items
    )
    history = state.get("dialectic_history", [])
    turn, usage = await arguer.aargue(
        active_focus,
        user_q,
        turn_index=len(history) + 1,
        evidence_summary=ev_summary,
    )
    meta = _merge_usage(meta, usage)
    return {
        "dialectic_history": history + [turn],
        "metadata": meta,
        "current_step": "DIALECTIC",
    }


async def gate_node(state: LegalCaseState):
    gate = LegalLogicGate()
    eval_res = gate.evaluate(state)
    if not eval_res.passed:
        return {
            "error_log": eval_res.reason,
            "current_step": "GATE_FAIL",
        }
    return {
        "error_log": None,
        "current_step": "GATE_PASS",
    }


async def human_evidence_node(state: LegalCaseState):
    """人工介入节点：主动挂起图执行，请用户补充缺失证据或确认跳过"""
    meta = dict(state.get("metadata") or {})
    missing = list(state.get("missing_evidence") or [])
    error_log = state.get("error_log")

    prompt_payload = {
        "type": "EVIDENCE_SUPPLEMENT_REQUIRED",
        "error_log": error_log,
        "missing_evidence": missing,
        "message": "请补充提交上述缺失证据内容（或输入“跳过”直接基于当前材料出具法官心证）。",
    }
    user_reply = str(interrupt(prompt_payload) or "").strip()

    meta["hitl_round"] = int(meta.get("hitl_round", 0)) + 1
    if not user_reply or any(k in user_reply for k in _SKIP_HINTS):
        meta["hitl_bypassed"] = True
        return {
            "metadata": meta,
            "is_awaiting_human": False,
            "current_step": "HUMAN_SKIPPED",
        }

    prev_q = meta.get("user_question", "")
    meta["user_question"] = f"{prev_q}\n\n【当事人补充举证/陈述】：{user_reply}".strip()
    meta["hitl_bypassed"] = False
    return {
        "metadata": meta,
        "is_awaiting_human": False,
        "current_step": "HUMAN_RESUMED",
    }


async def reporter_node(state: LegalCaseState):
    adjudicator = JudgeAdjudicator()
    meta = dict(state.get("metadata") or {})
    disposition, usage = await adjudicator.aadjudicate(
        state.get("dialectic_history", []),
        user_question=meta.get("user_question", ""),
        cause_of_action=meta.get("cause", "民间借贷纠纷"),
        evidence_items=state.get("evidence_items", []),
        gate_error=state.get("error_log"),
    )
    meta = _merge_usage(meta, usage)
    return {
        "final_disposition": disposition,
        "metadata": meta,
        "current_step": "REPORTER",
    }


def _needs_human_evidence(state: LegalCaseState) -> bool:
    meta = state.get("metadata") or {}
    if meta.get("hitl_bypassed") or int(meta.get("hitl_round", 0)) >= 1:
        return False
    if state.get("current_step") == "GATE_FAIL":
        return True
    ev_items = state.get("evidence_items", [])
    missing = state.get("missing_evidence", [])
    has_verified = any(
        (e.submission_status if hasattr(e, "submission_status") else e.get("submission_status")) == "已提交原件/核验"
        for e in ev_items
    )
    # 若没有任何已核验原件，且存在明确待补充凭证，则主动挂起提示用户补证
    return (not has_verified) and len(missing) > 0


def build_legal_graph(checkpointer: Optional[Any] = None, enable_hitl: bool = False):
    wf = StateGraph(LegalCaseState)
    wf.add_node("ALIGNER", aligner_node)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("DIALECTIC", dialectic_node)
    wf.add_node("GATE", gate_node)
    wf.add_node("REPORTER", reporter_node)

    wf.set_entry_point("ALIGNER")
    wf.add_edge("ALIGNER", "PLANNER")
    wf.add_edge("PLANNER", "DIALECTIC")
    wf.add_edge("DIALECTIC", "GATE")

    if enable_hitl:
        wf.add_node("HUMAN_EVIDENCE", human_evidence_node)
        wf.add_conditional_edges(
            "GATE",
            lambda s: "HUMAN_EVIDENCE" if _needs_human_evidence(s) else "REPORTER",
            {"HUMAN_EVIDENCE": "HUMAN_EVIDENCE", "REPORTER": "REPORTER"},
        )
        wf.add_conditional_edges(
            "HUMAN_EVIDENCE",
            lambda s: "REPORTER" if s.get("current_step") == "HUMAN_SKIPPED" else "ALIGNER",
            {"ALIGNER": "ALIGNER", "REPORTER": "REPORTER"},
        )
    else:
        wf.add_edge("GATE", "REPORTER")

    wf.add_edge("REPORTER", END)

    return wf.compile(checkpointer=checkpointer)
