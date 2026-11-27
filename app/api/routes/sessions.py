"""
app/api/routes/sessions.py
==========================
Thin controller for conversation session list, detail, rename/pin/archive,
cascade deletion, and manual/background title regeneration.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api.envelope import ResponseEnvelope
from app.core.memory.history import history_manager
from app.core.memory.session_store import session_store

router = APIRouter()


class SessionUpdateDTO(BaseModel):
    """Payload for updating session title, pinned flag, or archived flag."""

    title: Optional[str] = Field(default=None, description="Manual conversation title")
    pinned: Optional[bool] = Field(default=None, description="Pin conversation to top")
    archived: Optional[bool] = Field(default=None, description="Archive conversation")


def _extract_checkpointer(request: Request):
    app_state = getattr(getattr(request, "app", None), "state", None)
    return getattr(app_state, "saver", None) if app_state else None


@router.get("/agent/sessions")
@router.get("/ins-fqz/agent/sessions")
async def list_sessions(
    domain: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List paginated conversation sessions ordered by pinned status and recency."""
    result = session_store.list_sessions(
        domain=domain,
        query=q,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return ResponseEnvelope.success(data=result)


@router.get("/agent/sessions/{session_id}")
@router.get("/ins-fqz/agent/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Return session metadata together with filtered user/ai message history."""
    session = session_store.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    history = history_manager.get_history(session_id, auto_recover=False)
    messages = [
        {"role": "user" if msg.type == "human" else "ai", "content": msg.content}
        for msg in history
        if msg.type in ("human", "ai", "assistant")
    ]
    return ResponseEnvelope.success(data={**session, "messages": messages})


@router.patch("/agent/sessions/{session_id}")
@router.patch("/ins-fqz/agent/sessions/{session_id}")
async def patch_session(session_id: str, dto: SessionUpdateDTO):
    """Update session title (locking as manual), pinned flag, or archived flag."""
    updated = session_store.update_session(
        session_id,
        title=dto.title,
        pinned=dto.pinned,
        archived=dto.archived,
    )
    return ResponseEnvelope.success(data=updated)


@router.delete("/agent/sessions/{session_id}")
@router.delete("/ins-fqz/agent/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete session metadata, history JSON file, and LangGraph checkpointer thread."""
    checkpointer = _extract_checkpointer(request)
    deleted = await session_store.delete_session_cascade(
        session_id,
        history_mgr=history_manager,
        checkpointer=checkpointer,
    )
    if not deleted:
        raise KeyError(session_id)
    return ResponseEnvelope.success(data={"session_id": session_id, "deleted": True})


@router.post("/agent/sessions/{session_id}/regenerate-title")
@router.post("/ins-fqz/agent/sessions/{session_id}/regenerate-title")
async def regenerate_session_title(session_id: str, force: bool = Query(default=True)):
    """Regenerate session title using the async LLM title refiner."""
    session = session_store.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    history = history_manager.get_history(session_id, auto_recover=False)
    first_user = next((str(m.content) for m in history if m.type == "human"), "") or session["last_message_preview"]
    first_ai = next((str(m.content) for m in history if m.type in ("ai", "assistant")), "")
    await session_store.refine_title_in_background(
        session_id,
        first_user,
        first_ai,
        domain=session["domain"],
        force=force,
    )
    updated = session_store.get_session(session_id)
    return ResponseEnvelope.success(data=updated)
