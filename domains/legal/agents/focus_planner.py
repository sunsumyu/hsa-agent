"""
domains/legal/agents/focus_planner.py
=====================================
争议焦点三段论规划器（LLM 推理 + 法条注册表 + 确定性回退）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from domains.legal.state.case_state import DisputeFocus, SyllogismSlice
from domains.legal.registry.statute_registry import statute_registry
from domains.legal.agents.llm_client import ainvoke_legal_json


_PLANNER_SYSTEM_PROMPT = """你是一名资深民商事审判法官。请根据案由、案情陈述与法定构成要件，归纳本案的核心审判争议焦点，并进行三段论拆解。
请严格返回 JSON 格式：
{
  "foci": [
    {
      "issue_statement": "精准归纳的争议焦点表述",
      "governing_statutes": ["具体适用的法律/司法解释条文"],
      "adjudication_tendency": "当前材料下的初步裁判倾向",
      "confidence_score": 0.65,
      "elements": [
        {
          "element_name": "构成要件名称",
          "statute_basis": "法条依据",
          "is_satisfied": true,
          "vulnerability_notes": "举证薄弱点或风险提示"
        }
      ]
    }
  ]
}"""


class FocusPlanner:
    def plan(self, cause_of_action: str, user_input: str) -> List[DisputeFocus]:
        schema = statute_registry.get_cause_of_action(cause_of_action)
        foci: List[DisputeFocus] = []

        if "合意" in user_input or "借条" in user_input or "货款" in user_input or "投资" in user_input:
            slice_consensus = SyllogismSlice(
                element_id="consensus",
                element_name="借贷/交易合意",
                statute_basis="民法典第667条" if "借" in cause_of_action else "民法典第595条",
                is_satisfied=True,
            )
            foci.append(DisputeFocus(
                focus_id="FOCUS-01",
                issue_statement="双方之间款项往来性质系民间借贷合意还是其他基础法律关系"
                if "借" in cause_of_action
                else "标的物交付、验收与货款/违约金支付要件是否成就",
                cause_of_action=cause_of_action,
                governing_statutes=[
                    "最高人民法院关于审理民间借贷案件适用法律若干问题的规定第十六条"
                ] if "借" in cause_of_action else ["民法典第577条、第585条"],
                elements=[slice_consensus],
                adjudication_tendency="待对抗举证认定",
                confidence_score=0.6,
            ))

        if not foci:
            statute_hint = (
                f"{schema.governing_laws[0].name}{schema.governing_laws[0].article}"
                if (schema and schema.governing_laws)
                else "民法典合同编"
            )
            foci.append(DisputeFocus(
                focus_id="FOCUS-DEFAULT",
                issue_statement=f"{cause_of_action}成立要件与违约/还款责任认定",
                cause_of_action=cause_of_action,
                governing_statutes=[statute_hint],
                elements=[],
                adjudication_tendency="待综合认定",
                confidence_score=0.5,
            ))

        return foci

    async def aplan(
        self,
        cause_of_action: str,
        user_input: str,
    ) -> Tuple[List[DisputeFocus], Dict[str, Any]]:
        schema = statute_registry.get_cause_of_action(cause_of_action)
        statute_ctx = ""
        if schema:
            laws = [f"- {g.name}{g.article}（{g.title}）" for g in schema.governing_laws]
            elems = [
                f"- {el.name}（举证责任: {el.burden_of_proof}，可采证据: {', '.join(el.accepted_evidence_types)}）"
                for el in schema.essential_elements
            ]
            statute_ctx = "\n".join(laws + elems)
        prompt = (
            f"【涉案案由】：{cause_of_action}\n"
            f"【法定要件参考】：\n{statute_ctx or '民法典合同编一般规则'}\n\n"
            f"【案情陈述】：\n{user_input}"
        )
        data, usage = await ainvoke_legal_json(_PLANNER_SYSTEM_PROMPT, prompt)
        if not data or not isinstance(data.get("foci"), list):
            return self.plan(cause_of_action, user_input), usage

        foci: List[DisputeFocus] = []
        for idx, raw in enumerate(data["foci"], 1):
            if not isinstance(raw, dict) or not raw.get("issue_statement"):
                continue
            slices: List[SyllogismSlice] = []
            for e_idx, el in enumerate(raw.get("elements") or [], 1):
                if not isinstance(el, dict) or not el.get("element_name"):
                    continue
                slices.append(SyllogismSlice(
                    element_id=f"EL-{idx}-{e_idx}",
                    element_name=str(el["element_name"]),
                    statute_basis=str(el.get("statute_basis", "民法典相关规定")),
                    is_satisfied=bool(el.get("is_satisfied", False)),
                    vulnerability_notes=el.get("vulnerability_notes"),
                ))
            foci.append(DisputeFocus(
                focus_id=f"FOCUS-{idx:02d}",
                issue_statement=str(raw["issue_statement"]),
                cause_of_action=cause_of_action,
                governing_statutes=[str(s) for s in (raw.get("governing_statutes") or []) if s],
                elements=slices,
                adjudication_tendency=str(raw.get("adjudication_tendency", "待举证质证")),
                confidence_score=float(raw.get("confidence_score", 0.6)),
            ))

        if not foci:
            return self.plan(cause_of_action, user_input), usage
        return foci, usage
