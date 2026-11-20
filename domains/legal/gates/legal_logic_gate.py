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

        # 3. 诉讼时效与法定除斥期间门禁
        meta = state.get("metadata") or {}
        user_text = meta.get("user_question", "")
        all_narratives = " ".join(claims) + " " + user_text

        has_limitation_issue = any(
            k in all_narratives for k in ["逾期3年", "超过3年", "逾期四年", "逾期三年", "逾期4年", "一直未催告", "时效届满", "超过诉讼时效"]
        )
        has_demand_evidence = any(
            any(k in title for k in ["微信", "催告", "催款", "对账", "律师函", "中断", "履行请求"])
            for title in evidence_titles
        )
        if has_limitation_issue and not has_demand_evidence:
            return GateResult(
                passed=False,
                reason="诉讼时效届满风险预警：涉案债务已超过法定三年诉讼时效期间，且在案材料未见时效内催告或债务自认等中断凭证，面临严重败诉风险，建议补充时效中断证据。",
                error_code="ERR_LIMITATION_EXPIRED"
            )

        # 4. 利息上限门禁 (4倍 LPR 审查)
        import re
        interest_match = re.search(r"年(?:利(?:率)?)?[:：\s]*(\d+(?:\.\d+)?)%", all_narratives)
        if interest_match:
            try:
                rate = float(interest_match.group(1)) / 100.0
                usury_res = self.usury_eval.evaluate(rate, lpr_benchmark=0.0310, principal=100000.0)
                if usury_res.is_usurious and any(k in all_narratives for k in ["全部利息", "全部本息", "年利率36%", "按36%", "全额利息"]):
                    return GateResult(
                        passed=False,
                        reason=f"高额利息红线门禁拦截：{usury_res.clamping_notice} 建议调减利息诉求至法定4倍LPR以内。",
                        error_code="ERR_USURY_EXCEEDS_CEILING"
                    )
            except Exception:
                pass

        return GateResult(passed=True)
