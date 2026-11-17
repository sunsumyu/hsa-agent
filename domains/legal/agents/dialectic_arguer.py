"""
domains/legal/agents/dialectic_arguer.py
========================================
红蓝攻防对抗推演器（LLM 庭审辩论 + 确定性回退）。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple
from domains.legal.state.case_state import DisputeFocus, DialecticTurn
from domains.legal.agents.llm_client import ainvoke_legal_json


_DIALECTIC_SYSTEM_PROMPT = """你现在需要同时扮演民事诉讼法庭上的原告代理律师（红方）与被告代理律师（蓝方），并站在中立诉讼顾问视角给出举证突围策略。
要求：
1. 紧密结合具体案情细节、证据短板（例如未提交原件、口头抗辩无证据支撑、利率/违约金是否过高、是否过诉讼时效）展开攻防，严禁空泛套话。
2. 严禁虚构不存在的证据，缺失的证据应列入 required_evidence_patch。

请严格返回 JSON 格式：
{
  "plaintiff_stance": "原告攻击要件与请求权基础陈述",
  "defendant_defense": "被告针对性抗辩与举证反驳",
  "counter_strategy": "破局与庭审质证策略建议（含法条依据）",
  "required_evidence_patch": ["需要双方补充提交的具体证据项1", "证据项2"]
}"""


class DialecticArguer:
    def argue(self, focus: DisputeFocus, context: str, turn_index: int = 1) -> DialecticTurn:
        return DialecticTurn(
            turn_index=turn_index,
            target_focus_id=focus.focus_id,
            plaintiff_stance="原告主张请求权基础成立，应由被告承担相应给付或违约责任。",
            defendant_defense=f"被告提出事实抗辩：{context}，质疑原告举证充分性。",
            counter_strategy="依据举证责任分配规则，主张法律关系成立或变更的一方应提交客观书面/电子凭证；若仅停留在口头陈述而未质证原件，裁判风险较高。",
            required_evidence_patch=["补充书面合同/借条原件扫描件", "补充银行转账电子回单或履约交付凭证"],
        )

    async def aargue(
        self,
        focus: DisputeFocus,
        context: str,
        *,
        turn_index: int = 1,
        evidence_summary: str = "",
    ) -> Tuple[DialecticTurn, Dict[str, Any]]:
        prompt = (
            f"【争议焦点 ({focus.focus_id})】：{focus.issue_statement}\n"
            f"【适用法条】：{', '.join(focus.governing_statutes) or '民法典相关规定'}\n"
            f"【当前证据核验状态】：\n{evidence_summary or '尚无已核验原件'}\n\n"
            f"【案情上下文】：\n{context}"
        )
        data, usage = await ainvoke_legal_json(_DIALECTIC_SYSTEM_PROMPT, prompt)
        if not data or not data.get("plaintiff_stance"):
            return self.argue(focus, context, turn_index=turn_index), usage

        return DialecticTurn(
            turn_index=turn_index,
            target_focus_id=focus.focus_id,
            plaintiff_stance=str(data.get("plaintiff_stance", "")),
            defendant_defense=str(data.get("defendant_defense", "")),
            counter_strategy=str(data.get("counter_strategy", "")),
            required_evidence_patch=[
                str(x) for x in (data.get("required_evidence_patch") or []) if x
            ],
        ), usage
