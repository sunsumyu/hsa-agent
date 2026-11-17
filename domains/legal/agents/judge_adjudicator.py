from typing import List
from domains.legal.state.case_state import DialecticTurn

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
