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


_STATIC_FOCUS_SPECS: Tuple[Dict[str, Any], ...] = (
    {
        "cause_kws": ("建设工程",),
        "input_kws": ("施工", "工程款"),
        "element_id": "project_completion",
        "element_name": "工程竣工验收与工程款结算",
        "statute_basis": "民法典第791条、第807条",
        "issue_statement": "建设工程施工合同效力认定、实际施工人突破相对性追索及工程款结算依据是否充分",
        "governing_statutes": ["最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）第一条、第四十三条"],
        "adjudication_tendency": "待结合竣工验收及签证资料认定",
        "confidence_score": 0.65,
    },
    {
        "cause_kws": ("劳动",),
        "input_kws": ("二倍工资", "赔偿金", "辞退"),
        "element_id": "employment_relationship",
        "element_name": "劳动关系与违法解除赔偿",
        "statute_basis": "劳动合同法第82条、第87条",
        "issue_statement": "未订立书面劳动合同二倍工资差额起止期计算及解除劳动合同事由合法性审查",
        "governing_statutes": ["中华人民共和国劳动合同法第十条、第四十七条、第八十七条"],
        "adjudication_tendency": "待用人单位举证解除合法性",
        "confidence_score": 0.7,
    },
    {
        "cause_kws": ("交通事故",),
        "input_kws": ("交强险", "交警", "相撞"),
        "element_id": "insurance_compensation",
        "element_name": "交强险先行全额赔偿与商业险责任比例划分",
        "statute_basis": "民法典第1213条、交强险条例第21条",
        "issue_statement": "机动车交通事故中承保交强险保险公司是否应在法定责任限额内先行足额赔偿（不分过错打折），以及超出部分按过错比例在商业三者险内分担",
        "governing_statutes": [
            "中华人民共和国民法典第一千二百零八条、第一千二百一十三条",
            "最高人民法院指导案例第24号：荣宝英诉王阳、永诚财险案",
        ],
        "adjudication_tendency": "支持交强险限额内先行全额赔付，超出部分按主次责任分摊",
        "confidence_score": 0.85,
    },
    {
        "cause_kws": ("租赁",),
        "input_kws": ("退租", "商铺", "租金"),
        "element_id": "lease_termination_and_damages",
        "element_name": "提前退租解约效力、押金冲抵及违约金合理性审查",
        "statute_basis": "民法典第585条、第703条",
        "issue_statement": "承租人提前退租解约效力认定、押金是否应当冲抵退还，以及出租人主张的违约金是否过分高于其实际空置期合理损失",
        "governing_statutes": [
            "中华人民共和国民法典第五百八十五条第二款、第七百零三条",
            "最高人民法院关于审理城镇房屋租赁合同纠纷案件司法解释第六条",
        ],
        "adjudication_tendency": "待结合出租人减损义务及实际空置期损失依法酌减违约金",
        "confidence_score": 0.75,
    },
)


def _build_consensus_focus(cause_of_action: str) -> DisputeFocus:
    """构建借贷/买卖合意类争议焦点。"""
    is_loan = "借" in cause_of_action
    slice_consensus = SyllogismSlice(
        element_id="consensus",
        element_name="借贷/交易合意",
        statute_basis="民法典第667条" if is_loan else "民法典第595条",
        is_satisfied=True,
    )
    return DisputeFocus(
        focus_id="FOCUS-01",
        issue_statement=(
            "双方之间款项往来性质系民间借贷合意还是其他基础法律关系"
            if is_loan
            else "标的物交付、验收与货款/违约金支付要件是否成就"
        ),
        cause_of_action=cause_of_action,
        governing_statutes=[
            "最高人民法院关于审理民间借贷案件适用法律若干问题的规定第十六条"
        ] if is_loan else ["民法典第577条、第585条"],
        elements=[slice_consensus],
        adjudication_tendency="待对抗举证认定",
        confidence_score=0.6,
    )


def _build_default_focus(cause_of_action: str, schema: Any) -> DisputeFocus:
    """未命中专项模板时构建通用兜底争议焦点。"""
    statute_hint = (
        f"{schema.governing_laws[0].name}{schema.governing_laws[0].article}"
        if (schema and schema.governing_laws)
        else "民法典合同编"
    )
    return DisputeFocus(
        focus_id="FOCUS-DEFAULT",
        issue_statement=f"{cause_of_action}成立要件与违约/还款责任认定",
        cause_of_action=cause_of_action,
        governing_statutes=[statute_hint],
        elements=[],
        adjudication_tendency="待综合认定",
        confidence_score=0.5,
    )


class FocusPlanner:
    def plan(self, cause_of_action: str, user_input: str) -> List[DisputeFocus]:
        schema = statute_registry.get_cause_of_action(cause_of_action)
        for spec in _STATIC_FOCUS_SPECS:
            if any(k in cause_of_action for k in spec["cause_kws"]) or any(k in user_input for k in spec["input_kws"]):
                elem = SyllogismSlice(
                    element_id=spec["element_id"],
                    element_name=spec["element_name"],
                    statute_basis=spec["statute_basis"],
                    is_satisfied=True,
                )
                return [DisputeFocus(
                    focus_id="FOCUS-01",
                    issue_statement=spec["issue_statement"],
                    cause_of_action=cause_of_action,
                    governing_statutes=list(spec["governing_statutes"]),
                    elements=[elem],
                    adjudication_tendency=spec["adjudication_tendency"],
                    confidence_score=spec["confidence_score"],
                )]

        if any(k in user_input for k in ("合意", "借条", "货款", "投资")):
            return [_build_consensus_focus(cause_of_action)]
        return [_build_default_focus(cause_of_action, schema)]

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
