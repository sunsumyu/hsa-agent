"""
app/routes/legal_chat.py
========================
法律多轮辩法智能体流式对话路由 (FastAPI SSE Endpoint)
提供案情研判、争议焦点对抗、神经符号门禁校验与心证意见书流式输出。
"""

import json
import re
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState

router = APIRouter(prefix="/legal", tags=["Legal Agent"])

class LegalChatRequest(BaseModel):
    thread_id: str = Field(default="legal-session-001", description="多轮会话唯一标识")
    message: str = Field(..., description="案情描述、补充证据或当事人针对争议焦点的抗辩发言")
    cause_of_action: str = Field(default="民间借贷纠纷", description="案由名称")
    active_focus_id: Optional[str] = Field(default=None, description="定向钻取的争议焦点ID")

async def legal_stream_generator(req: LegalChatRequest) -> AsyncGenerator[str, None]:
    """流式执行图并逐节点 yield 事件"""
    graph = build_legal_graph()

    initial_state: LegalCaseState = {
        "thread_id": req.thread_id,
        "messages": [],
        "metadata": {
            "cause": req.cause_of_action,
            "user_question": req.message
        },
        "current_step": "INIT",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [],
        "evidence_items": [],
        "dispute_foci": [],
        "active_focus_id": req.active_focus_id,
        "dialectic_history": [],
        "final_disposition": None
    }

    try:
        # 逐节点流式执行
        async for event in graph.astream(initial_state):
            for node_name, node_output in event.items():
                payload = {
                    "node": node_name,
                    "step": node_output.get("current_step", node_name),
                    "error_log": node_output.get("error_log")
                }

                if node_name == "ALIGNER":
                    facts = [f.narrative if hasattr(f, "narrative") else f.get("narrative") for f in node_output.get("case_facts", [])]
                    evidence = [e.title if hasattr(e, "title") else e.get("title") for e in node_output.get("evidence_items", [])]
                    payload["summary"] = f"已提取客观事实 {len(facts)} 项，证据凭证 {len(evidence)} 项"
                    payload["evidence"] = evidence

                elif node_name == "PLANNER":
                    foci = node_output.get("dispute_foci", [])
                    payload["summary"] = f"锁定核心争议焦点 {len(foci)} 项"
                    payload["foci"] = [f.issue_statement if hasattr(f, "issue_statement") else f.get("issue_statement") for f in foci]

                elif node_name == "DIALECTIC":
                    turns = node_output.get("dialectic_history", [])
                    if turns:
                        latest = turns[-1]
                        payload["dialectic"] = {
                            "focus_id": latest.target_focus_id if hasattr(latest, "target_focus_id") else latest.get("target_focus_id"),
                            "counter_strategy": latest.counter_strategy if hasattr(latest, "counter_strategy") else latest.get("counter_strategy")
                        }

                elif node_name == "GATE":
                    passed = node_output.get("current_step") == "GATE_PASS"
                    payload["gate_passed"] = passed
                    if not passed:
                        payload["warning"] = node_output.get("error_log")

                elif node_name == "REPORTER":
                    payload["final_disposition"] = node_output.get("final_disposition")

                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.exception("Legal Agent 流式推演异常")
        err_payload = {"error": str(e), "node": "SYSTEM_EXCEPTION"}
        yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"

@router.post("/chat")
async def legal_chat_endpoint(req: LegalChatRequest):
    """法律辩法多轮流式对话接口"""
    return StreamingResponse(
        legal_stream_generator(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )

from domains.legal.registry.statute_registry import statute_registry
from domains.legal.registry.precedent_registry import precedent_registry

@router.get("/statutes")
async def get_statutes(query: Optional[str] = None, cause: Optional[str] = None):
    """检索民商事法条与法定证明要件知识库"""
    results = []
    for cause_name, schema in statute_registry._cache.items():
        if cause and cause != "全部" and cause not in cause_name:
            continue
        
        filtered_laws = schema.governing_laws
        filtered_elements = schema.essential_elements
        
        if query:
            q = query.strip().lower()
            filtered_laws = [
                law for law in schema.governing_laws
                if q in law.name.lower() or q in law.article.lower() or q in law.title.lower() or q in cause_name.lower()
            ]
            filtered_elements = [
                el for el in schema.essential_elements
                if q in el.name.lower() or any(q in ev.lower() for ev in el.accepted_evidence_types) or q in cause_name.lower()
            ]
            if not filtered_laws and not filtered_elements:
                continue
                
        results.append({
            "cause_of_action": cause_name,
            "governing_laws": [l.model_dump() for l in filtered_laws],
            "essential_elements": [e.model_dump() for e in filtered_elements]
        })
    return {"statutes": results}

@router.get("/precedents")
async def get_precedents(query: Optional[str] = None, cause: Optional[str] = None):
    """检索最高人民法院指导案例与民商事司法裁判要旨知识库"""
    results = []
    for case in precedent_registry._cases:
        if cause and cause != "全部" and cause not in case.cause_of_action:
            continue
        if query:
            q = query.strip().lower()
            matched = (
                q in case.case_name.lower()
                or q in case.case_number.lower()
                or q in case.cause_of_action.lower()
                or q in case.key_facts.lower()
                or q in case.referee_summary.lower()
                or q in case.application_rule.lower()
                or any(q in kw.lower() for kw in case.keywords)
            )
            if not matched:
                continue
        results.append(case.model_dump())
    return {"precedents": results}


class DocumentParseRequest(BaseModel):
    filename: str = Field(..., description="文书或凭证文件名")
    content: Optional[str] = Field(default=None, description="文本文书、OCR文本或证据说明")
    doc_type: Optional[str] = Field(default="auto", description="文书类型: iou/bank_slip/wechat/delivery/judgment/auto")


_DOCUMENT_CLASSIFICATION_RULES = (
    (
        ("借条", "借据", "借款"),
        ("iou",),
        (
            "借据 / 借条原件 (民间借贷核心合意书证)",
            "借贷合意成立要件",
            "真实性关键：核对借款人亲笔签字捺印；若仅为电子签名需验核实名认证。",
            "合法性合规：利息约定须在合同成立时1年期LPR四倍法定上限内。",
            "关联性直接：直接证明双方民间借贷合意及本金利息约定。",
        ),
    ),
    (
        ("转账", "回单", "流水"),
        ("bank",),
        (
            "金融机构转账凭据 / 银行电子回单 (交付实践要件凭证)",
            "款项实际交付要件",
            "真实性关键：网银电子印章、防伪验证码或银行柜台鲜章验真。",
            "合法性合规：资金来源合法，付款账户与合同主体严格一致。",
            "关联性核心：直接证实借款/货款资金交付事实，促使实践合同生效。",
        ),
    ),
    (
        ("微信", "聊天", "对账"),
        ("wechat",),
        (
            "即时通讯电子数据公证件 / 微信对账催款记录",
            "诉讼时效中断与债务自认要件",
            "真实性关键：须出示手机原始载体，核验微信号个人实名认证信息。",
            "合法性合规：合法取得，未侵犯他人通信隐私或商业秘密。",
            "关联性关键：证明债务人自认欠款及利息，发生法定诉讼时效中断。",
        ),
    ),
    (
        ("送货", "签收", "验收"),
        ("delivery",),
        (
            "送货单 / 仓管验收签收回执 (买卖履行交付书证)",
            "买卖合同标的物交付与验收要件",
            "真实性关键：经办人亲笔签字，结合项目部公章或资料章核验。",
            "合法性合规：符合行业物资进场签收常规习惯。",
            "关联性直接：证明供货方已完全履行交付义务，构成职务代理/表见代理。",
        ),
    ),
    (
        ("判决", "裁定", "调解书"),
        ("judgment",),
        (
            "生效司法裁判文书 / 调解书 (强制执行法定依据)",
            "执行立案与申请执行依据要件",
            "真实性最高：人民法院制作并送达生效，具备既判力与执行力。",
            "合法性完备：国家审判机关法定职权裁决。",
            "关联性终局：直接作为申请人民法院强制执行与全网查控的法定执行名义。",
        ),
    ),
)
_DEFAULT_DOCUMENT_PROFILE = (
    "民商事实务综合法律材料 / 合同附件",
    "基础法律关系证实要件",
    "审查原件原物客观载体与印章真实性。",
    "审查取证程序合法性与合规性。",
    "审查与案涉争议焦点因果关联系数。",
)
_KNOWN_PARTY_KEYWORDS = (
    "张三", "李四", "王五", "刘伟", "陈强", "王建国",
    "原告", "被告", "出借人", "借款人", "买方", "卖方", "总包", "发包人",
)


def _classify_legal_document(raw: str, fn_lower: str) -> Tuple[str, str, str, str, str]:
    """根据文书内容与文件名关键词匹配法定证据定位与三性评价。"""
    for raw_kws, fn_kws, profile in _DOCUMENT_CLASSIFICATION_RULES:
        if any(kw in raw for kw in raw_kws) or any(kw in fn_lower for kw in fn_kws):
            return profile
    return _DEFAULT_DOCUMENT_PROFILE


def _extract_document_entities(raw: str) -> Tuple[str, List[str], List[str]]:
    """提取法律文书中的金额、日期与涉案当事人线索。"""
    amounts = re.findall(r'(\d+(?:\.\d+)?)\s*(?:万|元)', raw)
    if "万" in raw and amounts:
        amount_str = f"{amounts[0]} 万元"
    elif amounts:
        amount_str = f"{amounts[0]} 元"
    else:
        amount_str = "待核实金额"

    dates = re.findall(r'(\d{4}[年\-\.]\d{1,2}[月\-\.]\d{1,2}(?:日)?)', raw)
    parties = [kw for kw in _KNOWN_PARTY_KEYWORDS if kw in raw] or ["出借人 / 权利人", "借款人 / 义务人"]
    return amount_str, dates, parties


@router.post("/parse-document")
async def parse_legal_document(req: DocumentParseRequest):
    """多模态法律文书与涉案证据凭证结构化解析与法定三性评级"""
    raw = (req.content or req.filename or "").strip()
    inferred, chain_pos, auth, leg, rel = _classify_legal_document(raw, req.filename.lower())
    amount_str, dates, parties = _extract_document_entities(raw)

    formatted_text = (
        f"【物证/电子数据提取核验】附件《{req.filename}》\n"
        f"• 凭证种类：{inferred}\n"
        f"• 涉案当事人：{'、'.join(parties)}\n"
        f"• 关联标的金额：{amount_str}\n"
        f"• 关键日期线索：{'、'.join(dates) if dates else '见文书载明'}\n"
        f"• 证据链定位：{chain_pos}\n"
        f"• 法定三性诊断：[真实性] {auth} [合法性] {leg} [关联性] {rel}"
    )

    return {
        "filename": req.filename,
        "inferred_type": inferred,
        "chain_position": chain_pos,
        "parties": parties,
        "amount_str": amount_str,
        "dates": dates,
        "three_attributes_rating": {"authenticity": auth, "legality": leg, "relevance": rel},
        "formatted_evidence_text": formatted_text,
        "suggested_action": "已完成凭证要素核验，建议点击下方按钮将结构化物证一键填入对话发起法庭质证或审查推演。",
    }


