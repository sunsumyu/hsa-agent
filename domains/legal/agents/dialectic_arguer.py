from domains.legal.state.case_state import DisputeFocus, DialecticTurn

class DialecticArguer:
    def argue(self, focus: DisputeFocus, context: str) -> DialecticTurn:
        return DialecticTurn(
            turn_index=1,
            target_focus_id=focus.focus_id,
            plaintiff_stance="原告已完成初步举证责任（转账凭单及催告事实），推定借贷合意成立。",
            defendant_defense=f"被告提出事实抗辩：{context}，试图推翻借贷合意。",
            counter_strategy="依《民间借贷司法解释》第十六条，被告抗辩双方系其他法律关系的，被告对其抗辩主张承担举证责任。若被告无法提供投资协议及分红结算账单，其抗辩不能成立。",
            required_evidence_patch=["要求被告限期提交投资项目章程/协议", "原告补充双方日常微信催息还款记录"]
        )
