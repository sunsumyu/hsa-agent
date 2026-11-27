"""
domains/legal/agents/judge_adjudicator.py
==========================================
法官终审心证评判生成器（LLM 裁判文书级评判 + 门禁意见融合 + 确定性回退）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from domains.legal.state.case_state import DialecticTurn, EvidenceItem
from domains.legal.agents.llm_client import ainvoke_legal_text
from domains.legal.registry.precedent_registry import precedent_registry


_ROLE_CONFIG = {
    "judge": {
        "title": "## ⚖️ 【法官心证评判】民商事案件裁判心证预判报告",
        "prompt": """你是一名经验丰富的中国民商事高级审判员。请以中立、权威、客观的裁判者视角，对涉案事实、法定构成要件、双方红蓝攻防及最高院指导案例进行全面评判。
要求：
1. 第一行以 `## ⚖️ 【法官心证评判】民商事案件裁判心证预判报告` 开头。
2. 审判员事实查明：明确区分哪些是已核验书证，哪些仅为当事人单方陈述。
3. 法律适用与构成要件裁定：依据三段论审查原告主张是否成立。
4. 结合最高院指导案例要旨进行同案同判说明。
5. 出具裁判主文预判（支持/部分支持/驳回）及诉讼风险提示。""",
    },
    "plaintiff": {
        "title": "## ⚔️ 【原告代理律师】诉求进攻与胜诉突破策略报告",
        "prompt": """你是一名极具攻击性和实战经验的原告方民商事诉讼律师。你的唯一目标是：最大化维护原告合法权益，帮助原告全额追索主张并彻底击溃被告的抗辩。
要求：
1. 第一行以 `## ⚔️ 【原告代理律师】诉求进攻与胜诉突破策略报告` 开头。
2. 请求权基础强化：指导原告如何夯实法律依据（主张借贷还是不当得利、突破合同相对性追索发包方等）。
3. 击溃被告抗辩方案：针对被告合伙投资、时效届满、货物瑕疵等抗辩，给出致命反驳策略与证据补强措施。
4. 诉讼财产保全指引：明确告知原告如何申请诉前/诉中财产保全冻结被告资产（防范转移财产）。
5. 诉请顶格优化建议：如何合法顶格主张逾期利息、违约金并由被告承担全部诉讼与保全费用。""",
    },
    "defendant": {
        "title": "## 🛡️ 【被告代理律师】应诉抗辩与防御狙击策略报告",
        "prompt": """你是一名精通诉讼攻防、善于寻找原告破绽的资深被告应诉律师。你的唯一目标是：为被告找到一切程序性与实体性抗辩突破口，驳回或大幅削减原告诉求。
要求：
1. 第一行以 `## 🛡️ 【被告代理律师】应诉抗辩与防御狙击策略报告` 开头。
2. 挖掘原告证据链致命硬伤：如原告仅有转账而无借条合意、送货单无合法授权签收人、未签劳动合同二倍工资已过仲裁时效等。
3. 程序性防线构筑：审查管辖权异议提出时机、原告主体适格性、是否应追加第三方。
4. 实体性狙击手段：详述诉讼时效届满抗辩、基础法律关系不符（如合伙款/定金/往来款抵销）、违约金过分高于损失申请司法酌减至LPR标准。
5. 反诉与抵销权线索挖掘：评估是否具备提起反诉或行使法定抵销权的事实基础。""",
    },
    "corporate": {
        "title": "## 🏢 【企业法务总监】商事追偿可行性与合规风控评估报告",
        "prompt": """你是一名大型企业集团法务合规总监。请站在企业商业利益最大化、控制诉讼沉没成本与合规风控的视角出具专业评估。
要求：
1. 第一行以 `## 🏢 【企业法务总监】商事追偿可行性与合规风控评估报告` 开头。
2. 追偿可行性与胜算评估：基于当前合同及履约留痕客观分析追偿成功概率。
3. 诉讼成本收益模型测算：对比诉讼费、保全成本、执行周期与实际回款概率，评估诉讼与和解的ROI。
4. 诉前正式追偿指引：起草一份规范的《商事催告清偿律师函/通知书草案》（明确清偿期限与法律后果）。
5. 业务端合同管理与留痕风控建议：指出当前业务人员在送货单签收、借条出具、对账单确认中的管理漏洞及补正措施。""",
    },
    "citizen": {
        "title": "## 🤝 【当事人维权助手】通俗白话维权指引与避坑清单",
        "prompt": """你是一名热心、专业的法律援助律师与群众维权导师。请完全摒弃晦涩的法言法语，用老百姓一听就懂的大白话进行保姆级辅导。
要求：
1. 第一行以 `## 🤝 【当事人维权助手】通俗白话维权指引与避坑清单` 开头。
2. 白话解答核心疑惑：直接告诉当事人“这个官司能不能赢、赢面有多大、钱能不能拿回来”。
3. 算笔明白账：用大白话列出需要花多少诉讼费、如果赢了钱由谁出、输了会不会赔很多。
4. 手把手去哪里立案：告诉当事人第一步带什么证件（身份证、凭证复印件）、去哪个法院立案大厅或微信小程序办理。
5. 证据收集与防坑指南：手把手教当事人如何从微信导出流水、如何补签借条对账单、千万不能犯的错误（如私自涂改、伪造日期）。""",
    },
}


class JudgeAdjudicator:
    def adjudicate(
        self,
        dialectic_history: List[DialecticTurn],
        *,
        cause_of_action: str = "民间借贷纠纷",
        user_question: str = "",
        user_role: str = "judge",
    ) -> str:
        role_cfg = _ROLE_CONFIG.get(user_role, _ROLE_CONFIG["judge"])
        lines = [f"{role_cfg['title']}\n"]
        for turn in dialectic_history:
            lines.append(f"### 争议焦点 {turn.target_focus_id} 攻防推演 (第 {turn.turn_index} 轮)")
            lines.append(f"- **原告主张面**: {turn.plaintiff_stance}")
            lines.append(f"- **被告抗辩点**: {turn.defendant_defense}")
            if user_role == "defendant":
                lines.append(f"- **【被告狙击与抗辩策略】**: {turn.counter_strategy}")
            elif user_role == "corporate":
                lines.append(f"- **【企业风控与催收策略】**: {turn.counter_strategy}")
            elif user_role == "citizen":
                lines.append(f"- **【维权提醒与避坑建议】**: {turn.counter_strategy}")
            else:
                lines.append(f"- **【原告反驳与攻防建议】**: {turn.counter_strategy}")
            if turn.required_evidence_patch:
                lines.append(f"- **待补充/调取证据清单**: {', '.join(turn.required_evidence_patch)}")
            lines.append("")

        matching = precedent_registry.match_precedents(cause_of_action, user_question, top_k=2)
        if matching:
            lines.append("### 🏛️ 最高人民法院指导性类案同判与裁判要旨参考\n")
            for p in matching:
                lines.append(
                    f"> [!NOTE]\n"
                    f"> **{p.case_name}**（{p.case_number}）\n"
                    f"> - **事实摘要**: {p.key_facts}\n"
                    f"> - **裁判要旨**: {p.referee_summary}\n"
                    f"> - **审判适用**: {p.application_rule}\n"
                )
        return "\n".join(lines)

    async def aadjudicate(
        self,
        dialectic_history: List[DialecticTurn],
        *,
        user_question: str,
        cause_of_action: str,
        evidence_items: List[EvidenceItem],
        gate_error: Optional[str] = None,
        user_role: str = "judge",
    ) -> Tuple[str, Dict[str, Any]]:
        role_cfg = _ROLE_CONFIG.get(user_role, _ROLE_CONFIG["judge"])
        ev_lines = [
            f"- {e.title}（{e.evidence_type} | 提交状态: {e.submission_status} | 效力: {e.authenticity_level}）"
            for e in evidence_items
        ] or ["- 暂无任何书面/电子证据提交"]
        turn_lines = [
            f"第{t.turn_index}轮 [{t.target_focus_id}]\n原告：{t.plaintiff_stance}\n被告：{t.defendant_defense}\n策略：{t.counter_strategy}"
            for t in dialectic_history
        ]

        matching_precedents = precedent_registry.match_precedents(cause_of_action, user_question, top_k=2)
        prec_text = "\n".join(
            f"- {p.case_name} ({p.case_number}):\n  要旨: {p.referee_summary}\n  规则: {p.application_rule}"
            for p in matching_precedents
        ) if matching_precedents else "无特定指导案例"

        prompt = (
            f"【目标角色视角】：{user_role}\n"
            f"【案由】：{cause_of_action}\n"
            f"【当事人陈述】：{user_question}\n"
            f"【最高院指导性案例库参考】：\n{prec_text}\n\n"
            f"【证据核验清单】：\n" + "\n".join(ev_lines) + "\n\n"
            f"【法理门禁结论】：{gate_error or '刚性门禁未发现实体法互斥或交付缺失问题（但仍需核验原件）'}\n\n"
            f"【红蓝对抗记录】：\n" + "\n\n".join(turn_lines)
        )
        text, usage = await ainvoke_legal_text(role_cfg["prompt"], prompt)
        if not text:
            return self.adjudicate(
                dialectic_history,
                cause_of_action=cause_of_action,
                user_question=user_question,
                user_role=user_role,
            ), usage
        if role_cfg["title"] not in text and "【" not in text:
            text = f"{role_cfg['title']}\n\n" + text

        # 若 LLM 未单独列出指导案例卡片，则自动附注标准最高院指导案例卡片
        if "指导案例" not in text and matching_precedents:
            prec_cards = ["\n\n### 🏛️ 最高人民法院指导性类案同判与裁判要旨参考\n"]
            for p in matching_precedents:
                prec_cards.append(
                    f"> [!NOTE]\n"
                    f"> **{p.case_name}**（{p.case_number}）\n"
                    f"> - **事实摘要**: {p.key_facts}\n"
                    f"> - **裁判要旨**: {p.referee_summary}\n"
                    f"> - **审判适用**: {p.application_rule}\n"
                )
            text += "".join(prec_cards)

        return text, usage
