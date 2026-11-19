from typing import Dict, Any
from cores.gates.base_gate import BaseSymbolicGate, GateResult
from domains.legal.gates.limitation_calculator import LimitationCalculator
from domains.legal.gates.usury_evaluator import UsuryEvaluator
from domains.legal.gates.estoppel_detector import EstoppelDetector
from domains.legal.registry.statute_registry import statute_registry

class LegalLogicGate(BaseSymbolicGate):
    def __init__(self):
        self.limitation_calc = LimitationCalculator()
        self.usury_eval = UsuryEvaluator()
        self.estoppel_detector = EstoppelDetector()

    def evaluate(self, state: Dict[str, Any]) -> GateResult:
        cause = state.get("metadata", {}).get("cause", "民间借贷纠纷")
        schema = statute_registry.get_cause_of_action(cause)

        evidence_items = state.get("evidence_items", [])
        evidence_titles = [
            e.title if hasattr(e, "title") else e.get("title", "")
            for e in evidence_items
        ]

        # 1. 实践合同款项交付硬门禁
        if schema and schema.get_element("actual_delivery"):
            has_delivery = any(
                any(k in title for k in ["转账", "流水", "回单", "收据", "支付", "汇款"])
                for title in evidence_titles
            )
            if not has_delivery:
                return GateResult(
                    passed=False,
                    reason="款项交付凭证缺失：自然人之间借贷属于实践合同，仅凭借条未提供转账流水或收条，交付要件未达成。",
                    error_code="ERR_DELIVERY_EVIDENCE_MISSING"
                )

        # 2. 诉求自相矛盾门禁
        claims = [
            f.narrative if hasattr(f, "narrative") else f.get("narrative", "")
            for f in state.get("case_facts", [])
        ]
        estoppel_res = self.estoppel_detector.evaluate(claims)
        if estoppel_res.has_contradiction:
            return GateResult(
                passed=False,
                reason=estoppel_res.explanation,
                error_code="ERR_ESTOPPEL_CONTRADICTION"
            )

        return GateResult(passed=True)
