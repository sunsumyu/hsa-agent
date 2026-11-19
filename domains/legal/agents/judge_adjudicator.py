"""
domains/legal/agents/judge_adjudicator.py
==========================================
法官终审心证评判生成器（LLM 裁判文书级评判 + 门禁意见融合 + 确定性回退）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from domains.legal.state.case_state import DialecticTurn, EvidenceItem
from domains.legal.agents.llm_client import ainvoke_legal_text


_JUDGE_SYSTEM_PROMPT = """你是一名经验丰富的中国民商事审判员。请综合双方红蓝对抗要点、当前证据核验状态以及法理门禁审查意见，撰写一份专业、克制、有实操价值的【法官心证评判】与辩法意见书。
要求：
1. 第一行必须以 `## 【法官心证评判】与辩法意见书` 开头。
2. 明确指出当前哪些证据属于"仅口头提及、尚未实际提交核验"，不得将其当作已查明铁证。
3. 如果存在法理门禁拦截/风险提示（如缺款项交付凭证、高息截断、诉讼时效届满、诉求自相矛盾），必须在心证结论中给出刚性法律后果分析与补救建议。
4. 给出双方胜诉/败诉风险点及下一步具体举证/诉讼策略清单。"""


class JudgeAdjudicator:
    def adjudicate(self, dialectic_history: List[DialecticTurn]) -> str:
        lines = ["## 【法官心证评判】与辩法意见书\n"]
        for turn in dialectic_history:
            lines.append(f"### 争议焦点 {turn.target_focus_id} 攻防推演 (第 {turn.turn_index} 轮)")
            lines.append(f"- **原告主张面**: {turn.plaintiff_stance}")
            lines.append(f"- **被告抗辩点**: {turn.defendant_defense}")
            lines.append(f"- **【原告反驳与攻防建议】**: {turn.counter_strategy}")
            if turn.required_evidence_patch:
                lines.append(f"- **待补充/调取证据清单**: {', '.join(turn.required_evidence_patch)}")
            lines.append("")
        return "\n".join(lines)

    async def aadjudicate(
        self,
        dialectic_history: List[DialecticTurn],
        *,
        user_question: str,
        cause_of_action: str,
        evidence_items: List[EvidenceItem],
        gate_error: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        ev_lines = [
            f"- {e.title}（{e.evidence_type} | 提交状态: {e.submission_status} | 效力: {e.authenticity_level}）"
            for e in evidence_items
        ] or ["- 暂无任何书面/电子证据提交"]
        turn_lines = [
            f"第{t.turn_index}轮 [{t.target_focus_id}]\n原告：{t.plaintiff_stance}\n被告：{t.defendant_defense}\n策略：{t.counter_strategy}"
            for t in dialectic_history
        ]
        prompt = (
            f"【案由】：{cause_of_action}\n"
            f"【当事人陈述】：{user_question}\n"
            f"【证据核验清单】：\n" + "\n".join(ev_lines) + "\n\n"
            f"【法理门禁结论】：{gate_error or '刚性门禁未发现实体法互斥或交付缺失问题（但仍需核验原件）'}\n\n"
            f"【红蓝对抗记录】：\n" + "\n\n".join(turn_lines)
        )
        text, usage = await ainvoke_legal_text(_JUDGE_SYSTEM_PROMPT, prompt)
        if not text:
            return self.adjudicate(dialectic_history), usage
        if "【法官心证评判】" not in text:
            text = "## 【法官心证评判】与辩法意见书\n\n" + text
        return text, usage
