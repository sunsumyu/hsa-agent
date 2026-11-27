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
        issue = focus.issue_statement or ""
        cause = focus.cause_of_action or ""

        if "交通事故" in cause or "交强险" in issue or "交通事故" in context:
            return DialecticTurn(
                turn_index=turn_index,
                target_focus_id=focus.focus_id,
                plaintiff_stance="原告主张机动车交通事故侵权事实清楚，保险公司应在交强险责任限额（医疗费1.8万+伤残18万）内全额先行赔偿，超出部分按80%商业险理赔。",
                defendant_defense="保险公司抗辩称受害人自身存在交通违法行为负次要责任，依据过错相抵原则，全部医疗与伤残赔偿款均应扣减20%过错比例。",
                counter_strategy="援引最高法指导案例第24号及民法典第1213条：交强险法定限额内先行足额全额赔付，不按过错比例打折，仅扣除交强险后的超出部分方按主责商业险分担。",
                required_evidence_patch=["补充道路交通事故认定书原件", "补充医疗费发票原件与用药明细清单", "补充司法伤残鉴定意见书"],
            )
        elif "租赁" in cause or "退租" in issue or "租金" in context:
            return DialecticTurn(
                turn_index=turn_index,
                target_focus_id=focus.focus_id,
                plaintiff_stance="出租人主张承租人提前退租构成根本违约，依据合同约定应当没收全部押金并赔偿剩余租期全部未付租金及高额违约金。",
                defendant_defense="承租人抗辩称已腾退交房且出租人负有减损义务，出租人已重新挂牌另行出租，违约金过分高于实际损失，请求调减并冲抵退还押金。",
                counter_strategy="依据民法典第585条及城镇房屋租赁司法解释，出租人负有防止损失扩大的减损义务，违约金应以实际合理空置期损失（通常1-3个月）为限依法调减。",
                required_evidence_patch=["补充房屋租赁合同及退租交接备忘录", "补充出租人重新挂牌出租及实际起租日期凭据", "补充物业水电费结清发票"],
            )
        elif "劳动" in cause or "二倍工资" in issue or "辞退" in context:
            return DialecticTurn(
                turn_index=turn_index,
                target_focus_id=focus.focus_id,
                plaintiff_stance="劳动者主张事实用工关系明确，用人单位未签书面合同应支付二倍工资差额，且未履行法定预告及工会程序单方辞退构成违法解除，应支付2N赔偿金。",
                defendant_defense="用人单位抗辩称劳动者存在严重违纪、无法胜任工作，或离职已超过法定一年劳动争议仲裁时效。",
                counter_strategy="依据劳动合同法第10条、第82条、第87条，事实劳动关系凭工资流水与打卡记录推定，未履行工会前置程序的辞退直接认定为违法解除。",
                required_evidence_patch=["补充银行代发薪资流水明细", "补充钉钉打卡考勤与工作审批公证书", "补充解除劳动合同通知或移出工作群记录"],
            )
        elif "建设工程" in cause or "实际施工人" in issue or "工程款" in context:
            return DialecticTurn(
                turn_index=turn_index,
                target_focus_id=focus.focus_id,
                plaintiff_stance="实际施工人主张工程已竣工验收合格并交付使用，突破合同相对性请求发包人在欠付总承包工程款范围内承担直接清偿付款责任。",
                defendant_defense="发包人抗辩称与实际施工人无合同关系，或总包工程存在质量瑕疵尚未进行最终审定结算。",
                counter_strategy="援引最高法指导案例第103号及建工解释(一)第43条：工程经竣工验收合格，发包人在欠付工程款范围内对实际施工人负直接给付清偿义务。",
                required_evidence_patch=["补充五方竣工验收合格备案表", "补充三方工程结算审核协议或发包人欠付工程款核算单"],
            )

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
