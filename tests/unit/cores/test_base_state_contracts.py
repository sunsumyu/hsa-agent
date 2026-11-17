import pytest
from cores.state.base import BaseCognitiveState
from cores.gates.base_gate import BaseSymbolicGate, GateResult

def test_base_cognitive_state_structure():
    state: BaseCognitiveState = {
        "thread_id": "thread-001",
        "messages": [],
        "metadata": {"task": "demo"},
        "current_step": "ALIGNER",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False
    }
    assert state["thread_id"] == "thread-001"
    assert state["retry_count"] == 0

def test_base_symbolic_gate_interface():
    class DummyGate(BaseSymbolicGate):
        def evaluate(self, state: BaseCognitiveState) -> GateResult:
            if state.get("error_log"):
                return GateResult(passed=False, reason="Error exists", error_code="ERR_EXISTS")
            return GateResult(passed=True)

    gate = DummyGate()
    ok_res = gate.evaluate({
        "thread_id": "t1",
        "messages": [],
        "metadata": {},
        "current_step": "STEP",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False
    })
    assert ok_res.passed is True
    assert ok_res.reason is None

    fail_res = gate.evaluate({
        "thread_id": "t2",
        "messages": [],
        "metadata": {},
        "current_step": "STEP",
        "error_log": "boom",
        "retry_count": 0,
        "is_awaiting_human": False
    })
    assert fail_res.passed is False
    assert fail_res.error_code == "ERR_EXISTS"
