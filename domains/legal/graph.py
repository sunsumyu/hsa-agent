from langgraph.graph import StateGraph, END
from domains.legal.state.case_state import LegalCaseState
from domains.legal.agents.fact_extractor import FactExtractor
from domains.legal.agents.focus_planner import FocusPlanner
from domains.legal.agents.dialectic_arguer import DialecticArguer
from domains.legal.agents.judge_adjudicator import JudgeAdjudicator
from domains.legal.gates.legal_logic_gate import LegalLogicGate

async def aligner_node(state: LegalCaseState):
    extractor = FactExtractor()
    user_q = state.get("metadata", {}).get("user_question", "")
    facts, evidence = extractor.extract(user_q)
    return {
        "case_facts": facts,
        "evidence_items": evidence,
        "current_step": "ALIGNER"
    }

async def planner_node(state: LegalCaseState):
    planner = FocusPlanner()
    cause = state.get("metadata", {}).get("cause", "民间借贷纠纷")
    user_q = state.get("metadata", {}).get("user_question", "")
    foci = planner.plan(cause, user_q)
    return {
        "dispute_foci": foci,
        "active_focus_id": foci[0].focus_id if foci else None,
        "current_step": "PLANNER"
    }

async def dialectic_node(state: LegalCaseState):
    arguer = DialecticArguer()
    foci = state.get("dispute_foci", [])
    active_focus = foci[0] if foci else None
    user_q = state.get("metadata", {}).get("user_question", "")
    turn = arguer.argue(active_focus, user_q)
    return {
        "dialectic_history": state.get("dialectic_history", []) + [turn],
        "current_step": "DIALECTIC"
    }

async def gate_node(state: LegalCaseState):
    gate = LegalLogicGate()
    eval_res = gate.evaluate(state)
    if not eval_res.passed:
        return {
            "error_log": eval_res.reason,
            "current_step": "GATE_FAIL"
        }
    return {
        "error_log": None,
        "current_step": "GATE_PASS"
    }

async def reporter_node(state: LegalCaseState):
    adjudicator = JudgeAdjudicator()
    disposition = adjudicator.adjudicate(state.get("dialectic_history", []))
    return {
        "final_disposition": disposition,
        "current_step": "REPORTER"
    }

def build_legal_graph():
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
    wf.add_edge("GATE", "REPORTER")
    wf.add_edge("REPORTER", END)

    return wf.compile()
