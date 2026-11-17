from typing import List, Tuple
from domains.legal.state.case_state import CaseFact, EvidenceItem

class FactExtractor:
    def extract(self, text: str) -> Tuple[List[CaseFact], List[EvidenceItem]]:
        evidence_list = []
        facts_list = []

        if "转账" in text or "流水" in text or "回单" in text:
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="银行转账凭单",
                evidence_type="电子数据",
                content_summary="证明出借人资金交付流水事实",
                authenticity_level="高"
            ))

        if "借条" in text or "欠条" in text or "协议" in text:
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="借款凭据原件",
                evidence_type="书证",
                content_summary="证明双方成立借贷合意",
                authenticity_level="高"
            ))

        facts_list.append(CaseFact(
            fact_id=f"FACT-{len(facts_list)+1:02d}",
            narrative=text.strip(),
            evidence_anchors=[e.evidence_id for e in evidence_list]
        ))

        return facts_list, evidence_list
