"""
domains/legal/agents/fact_extractor.py
======================================
案情事实与证据凭证抽取器（LLM 语义抽取 + 确定性防幻觉兜底）。
严格区分"当事人陈述提及（待提交核验）"与"已实际提交/质证"，防止无中生有。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from domains.legal.state.case_state import CaseFact, EvidenceItem
from domains.legal.agents.llm_client import ainvoke_legal_json


_NEGATION_RE = re.compile(r"(?:无|没有|未|缺少|缺失|丢失|无法提供|拿不出)[^，。；,.]{0,8}")
_SUBMITTED_HINTS = (
    "已提交", "已上传", "已补充", "补充提交", "附上", "附有", "提交了原件", "经质证", "已核验",
    "【证据", "【借条", "【欠条", "【银行", "电子回单", "回单编号", "签字捺印", "送货签收单", "转账附言",
    "聊天记录", "单据编号"
)

_FACT_SYSTEM_PROMPT = """你是一名严谨的中国民商事审判书记员与证据审查专家。请从当事人的陈述与出具的凭证文本中抽取客观事实与证据状态，并严格遵守防幻觉规则：
1. 只能抽取文本中明确陈述或出具的事实，严禁脑补未提及的时间、金额或凭证。
2. 严格区分"仅口头陈述提及"与"已出具/提交证据文本"：
   - 如果用户仅口头单方主张"有借条""留有银行回单""双方有转账记录"，但并未出具具体的凭证文本内容，必须将 submission_status 设为 "仅口头陈述提及（待提交）"，authenticity_level 设为 "存疑"。
   - 如果用户出具了具体的票据凭证文本（如载有出借人/借款人、借款条款、签字捺印的借条文本，或载有回单编号、付款人、收款人、转账金额与附言的银行电子回单，或微信催款记录文本，或送货签收单等），或明确表示"已提交原件/出具凭证文本/经质证确认"，必须将 submission_status 设为 "已提交原件/核验"，authenticity_level 设为 "高"，并提取其关键证明要素。
3. 遇到否定句（如"没有转账记录""无借条""无法提供收条""拿不出合伙协议"），严禁生成该证据项！必须将该项列入 missing_evidence。

请严格返回如下 JSON 格式：
{
  "facts": [
    {"narrative": "客观事实陈述", "fact_time": "YYYY-MM-DD或null", "is_disputed": true}
  ],
  "evidence": [
    {
      "title": "证据名称（如：招商银行电子回单、借条原件文本）",
      "evidence_type": "书证|电子数据|视听资料|证人证言|当事人陈述",
      "content_summary": "待证明内容及关键记载（如收款人、金额、附言、借款人签字）",
      "amount": null,
      "authenticity_level": "存疑|中|高",
      "submission_status": "仅口头陈述提及（待提交）|已提交原件/核验|缺失/待补充"
    }
  ],
  "missing_evidence": ["缺失或需补充提交的关键凭证清单（若已提交相应凭证原件文本，此处应为空数组）"]
}"""


def _is_negated(text: str, keyword: str) -> bool:
    for m in re.finditer(re.escape(keyword), text):
        prefix = text[max(0, m.start() - 10) : m.start()]
        if not _NEGATION_RE.search(prefix):
            return False
    return True


def _has_keyword_affirmatively(text: str, keywords: Tuple[str, ...]) -> bool:
    return any((kw in text) and not _is_negated(text, kw) for kw in keywords)


class FactExtractor:
    def extract_with_missing(self, text: str) -> Tuple[List[CaseFact], List[EvidenceItem], List[str]]:
        evidence_list: List[EvidenceItem] = []
        missing_list: List[str] = []
        is_submitted = any(h in text for h in _SUBMITTED_HINTS)
        sub_status = "已提交原件/核验" if is_submitted else "仅口头陈述提及（待提交）"
        auth_level = "中" if is_submitted else "存疑"

        if _has_keyword_affirmatively(text, ("转账", "流水", "回单", "汇款")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="银行转账凭单（陈述提及）" if not is_submitted else "银行转账凭单",
                evidence_type="电子数据",
                content_summary="待核验出借人/付款方资金交付流水事实",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))
        elif any(k in text for k in ("转账", "流水", "回单", "现金交付")):
            missing_list.append("银行转账流水 / 收款收据原件（当前缺乏资金实际交付凭证）")

        if _has_keyword_affirmatively(text, ("借条", "欠条", "借款协议", "买卖合同", "合同")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="借据/合同文本（陈述提及）" if not is_submitted else "借据/合同原件",
                evidence_type="书证",
                content_summary="待核验双方合意及权利义务条款",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))
        elif any(k in text for k in ("借条", "欠条", "协议", "合同")):
            missing_list.append("借条 / 书面合同原件")

        if _has_keyword_affirmatively(text, ("微信", "聊天记录", "催款")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="微信催款及债务确认记录",
                evidence_type="电子数据",
                content_summary="当事人沟通记录（证明还款催告与诉讼时效中断）",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if _has_keyword_affirmatively(text, ("送货", "签收", "收货单", "入库单")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="物资送货签收单",
                evidence_type="书证",
                content_summary="买卖合同履行（货物送达及收货方盖章签收）",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if _has_keyword_affirmatively(text, ("事故认定", "交警认定", "医疗费发票", "伤残鉴定", "交强险", "保单")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="交通事故责任认定书及医疗损害鉴定材料",
                evidence_type="书证",
                content_summary="证明侵权事实、交警责任划分比例、保险承保情况及人身损害诊疗支出",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if _has_keyword_affirmatively(text, ("租赁合同", "租房合同", "押金收据", "押金收条", "退租交接", "房屋交接", "钥匙移交")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="房屋租赁合同及退租交接凭据",
                evidence_type="书证",
                content_summary="证明租赁关系成立、押金交付、租期解除通知及房屋实际腾退交付状态",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if _has_keyword_affirmatively(text, ("竣工验收", "工程结算", "工程价款审核", "实际施工人", "挂靠")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="建设工程施工与竣工结算审核资料",
                evidence_type="书证",
                content_summary="证明建设工程五方验收合格、审定工程总造价及发承包人欠款数额",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if _has_keyword_affirmatively(text, ("代发工资", "工资流水", "钉钉打卡", "考勤记录", "解除通知", "离职证明", "移出工作群")):
            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title="劳动关系存续与单方解除用工凭证",
                evidence_type="电子数据",
                content_summary="证明事实劳动关系用工事实、发放工资标准及单方违法辞退事实",
                authenticity_level=auth_level,
                submission_status=sub_status,
            ))

        if not is_submitted and evidence_list:
            missing_list.append("上述陈述提及凭证的扫描件/原件核验材料")

        facts_list = [
            CaseFact(
                fact_id="FACT-01",
                narrative=text.strip(),
                evidence_anchors=[e.evidence_id for e in evidence_list],
            )
        ]
        return facts_list, evidence_list, missing_list

    def extract(self, text: str) -> Tuple[List[CaseFact], List[EvidenceItem]]:
        facts, evidence, _ = self.extract_with_missing(text)
        return facts, evidence

    async def aextract(self, text: str) -> Tuple[List[CaseFact], List[EvidenceItem], List[str], Dict[str, Any]]:
        data, usage = await ainvoke_legal_json(_FACT_SYSTEM_PROMPT, f"当事人案情陈述：\n{text}")
        if not data or not isinstance(data.get("facts"), list):
            facts, evidence, missing = self.extract_with_missing(text)
            return facts, evidence, missing, usage

        evidence_list: List[EvidenceItem] = []
        valid_types = {"书证", "电子数据", "视听资料", "证人证言", "当事人陈述"}
        valid_auth = {"高", "中", "存疑"}
        valid_sub = {"已提交原件/核验", "仅口头陈述提及（待提交）", "缺失/待补充"}

        for raw_ev in data.get("evidence", []) or []:
            if not isinstance(raw_ev, dict) or not raw_ev.get("title"):
                continue
            ev_type = raw_ev.get("evidence_type", "书证")
            if ev_type not in valid_types:
                ev_type = "书证"
            sub = raw_ev.get("submission_status", "仅口头陈述提及（待提交）")
            if sub not in valid_sub:
                sub = "仅口头陈述提及（待提交）"
            auth = raw_ev.get("authenticity_level", "存疑")
            if auth not in valid_auth:
                auth = "存疑"
            # 硬性防幻觉兜底：未实际提交时不得标为"高"
            if sub != "已提交原件/核验" and auth == "高":
                auth = "存疑"

            evidence_list.append(EvidenceItem(
                evidence_id=f"EVD-{len(evidence_list)+1:02d}",
                title=str(raw_ev["title"]),
                evidence_type=ev_type,
                content_summary=str(raw_ev.get("content_summary", "待质证核验")),
                authenticity_level=auth,
                submission_status=sub,
            ))

        facts_list: List[CaseFact] = []
        for raw_f in data.get("facts", []) or []:
            if not isinstance(raw_f, dict) or not raw_f.get("narrative"):
                continue
            facts_list.append(CaseFact(
                fact_id=f"FACT-{len(facts_list)+1:02d}",
                narrative=str(raw_f["narrative"]),
                fact_time=raw_f.get("fact_time"),
                evidence_anchors=[e.evidence_id for e in evidence_list],
                is_disputed=bool(raw_f.get("is_disputed", False)),
            ))

        if not facts_list:
            facts_list = [CaseFact(fact_id="FACT-01", narrative=text.strip())]

        missing = [str(m) for m in (data.get("missing_evidence") or []) if m]
        return facts_list, evidence_list, missing, usage
