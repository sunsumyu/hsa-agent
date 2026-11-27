"""
app/routes/graph_state.py
=========================
图状态管理路由: update_state / fork_session.
各端点底层委托至 graph_state_orchestrator 深模块。
"""

from fastapi import APIRouter, Request
from app.orchestration.graph_state_orchestrator import graph_state_orchestrator
from app.api.envelope import ResponseEnvelope

router = APIRouter()


@router.post("/agent/update_state")
@router.post("/ins-fqz/agent/update_state")
async def update_state(request: Request):
    """人工干预接口：修改指定会话的中间状态 (Debug Mode)"""
    data = await request.json()
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    findings = data.get("findings")

    app_state = getattr(getattr(request, "app", None), "state", None)
    checkpointer = getattr(app_state, "saver", None) if app_state else None

    result = await graph_state_orchestrator.intervene_findings(
        session_id=session_id,
        findings=findings,
        checkpointer=checkpointer,
    )
    return ResponseEnvelope.from_result(result)


@router.post("/agent/fork")
@router.post("/ins-fqz/agent/fork")
async def fork_session(request: Request):
    """会话分叉接口：克隆当前会话到新 Thread (A/B Test)"""
    data = await request.json()
    source_session = data.get("sourceSessionId")
    target_session = data.get("targetSessionId")

    app_state = getattr(getattr(request, "app", None), "state", None)
    checkpointer = getattr(app_state, "saver", None) if app_state else None

    result = await graph_state_orchestrator.fork_session(
        source_session=source_session,
        target_session=target_session,
        checkpointer=checkpointer,
    )
    return ResponseEnvelope.from_result(result)
