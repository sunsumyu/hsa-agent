"""
app/routes/palace.py
====================
MemPalace 相关端点: 证据拓扑图谱 / 记忆时间轴 / 冲突检测与解决。
薄控制器设计 (Thin Controller)，接入统一 ResponseEnvelope，实现细节委托给深模块:
- graph_state_orchestrator (图状态与时间轴编排)
- evidence_graph_manager (证据知识图谱与多会话冲突提取)
"""

from typing import Optional
from fastapi import APIRouter, Request
from loguru import logger

from app.core.graph_state_orchestrator import graph_state_orchestrator
from app.memory.entity_extractor import evidence_graph_manager
from app.core.schemas import ResolveRequest
from app.api.envelope import ResponseEnvelope

router = APIRouter()


@router.get("/palace/graph")
@router.get("/ins-fqz/palace/graph")
async def get_palace_graph(session_id: Optional[str] = None):
    """[V4.9.6] MemPalace 证据拓扑图谱：将最近推演的 Findings 解析为可视化图结构"""
    return evidence_graph_manager.get_session_graph(session_id)


@router.get("/palace/timeline")
@router.get("/ins-fqz/palace/timeline")
async def get_palace_timeline(request: Request, session_id: str = "default_session"):
    """[V4.9.6] MemPalace 记忆时间轴：获取 Agent 推演时的离散记忆切片"""
    try:
        app_state = getattr(getattr(request, "app", None), "state", None)
        saver = getattr(app_state, "saver", None) if app_state else None
        events = await graph_state_orchestrator.get_timeline_events(session_id, checkpointer=saver)
        return ResponseEnvelope.success(session_id=session_id, events=events)
    except Exception as e:
        logger.error(f"Error fetching timeline: {e}")
        return ResponseEnvelope.error(error=str(e), session_id=session_id, events=[], status_code=500)


@router.get("/palace/conflicts")
@router.get("/ins-fqz/palace/conflicts")
async def api_get_conflicts(session_id: Optional[str] = None):
    """[V4.9.6] 检测当前记忆系统（或指定会话）中的逻辑冲突"""
    conflicts = evidence_graph_manager.detect_session_conflicts(session_id)
    return ResponseEnvelope.success(conflicts=conflicts)


@router.post("/palace/conflicts/resolve")
@router.post("/ins-fqz/palace/conflicts/resolve")
async def api_resolve_conflict(req: ResolveRequest):
    """[V4.9.6] 用户手动解决证据冲突"""
    from app.skills.conflict_detector import mark_resolved

    mark_resolved(req.finding_a, req.keep_a)
    mark_resolved(req.finding_b, req.keep_b)
    return ResponseEnvelope.success(status="success", message="冲突已解决")
