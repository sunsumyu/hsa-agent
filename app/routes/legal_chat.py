"""
app/routes/legal_chat.py
========================
法律多轮辩法智能体流式对话路由 (FastAPI SSE Endpoint)
提供案情研判、争议焦点对抗、神经符号门禁校验与心证意见书流式输出。
"""

import json
from typing import Optional, List, Dict, Any, AsyncGenerator
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

