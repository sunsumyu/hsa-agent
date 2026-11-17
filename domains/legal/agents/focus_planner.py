from typing import List
from domains.legal.state.case_state import DisputeFocus, SyllogismSlice
from domains.legal.registry.statute_registry import statute_registry

class FocusPlanner:
    def plan(self, cause_of_action: str, user_input: str) -> List[DisputeFocus]:
        schema = statute_registry.get_cause_of_action(cause_of_action)
        foci = []

        if "合意" in user_input or "借条" in user_input or "货款" in user_input:
            slice_consensus = SyllogismSlice(
                element_id="consensus",
                element_name="借贷合意",
                statute_basis="民法典第667条",
                is_satisfied=True
            )
            foci.append(DisputeFocus(
                focus_id="FOCUS-01",
                issue_statement="双方之间款项往来性质系民间借贷合意还是其他基础法律关系",
                cause_of_action=cause_of_action,
                governing_statutes=["最高人民法院关于审理民间借贷案件适用法律若干问题的规定第十六条"],
                elements=[slice_consensus],
                adjudication_tendency="待对抗举证认定",
                confidence_score=0.6
            ))

        if not foci:
            foci.append(DisputeFocus(
                focus_id="FOCUS-DEFAULT",
                issue_statement="民间借贷成立要件与还款责任认定",
                cause_of_action=cause_of_action,
                elements=[],
                adjudication_tendency="待综合认定",
                confidence_score=0.5
            ))

        return foci
