"""
app/routes/palace.py
====================
MemPalace 相关端点: 证据拓扑图谱 / 记忆时间轴 / 冲突检测与解决。
从 main.py 提取，保持 API 路径不变。
"""

from fastapi import APIRouter
from loguru import logger
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent_graph import get_graph_executor
from app.schemas import ResolveRequest

router = APIRouter()


@router.get("/palace/graph")
@router.get("/ins-fqz/palace/graph")
async def get_palace_graph(session_id: str = None):
    """[V4.9.6] MemPalace 证据拓扑图谱：将最近推演的 Findings 解析为可视化图结构"""
    from app.entity_extractor import get_latest_graph
    graph = get_latest_graph(session_id)
    return graph


@router.get("/palace/timeline")
@router.get("/ins-fqz/palace/timeline")
async def get_palace_timeline(session_id: str = "default_session"):
    """[V4.9.6] MemPalace 记忆时间轴：获取 Agent 推演时的离散记忆切片"""
    try:
        async with AsyncSqliteSaver.from_conn_string("audit_checkpoints.db") as saver:
            # [Bug fix V90.0] get_graph_executor 返回 (executor, model_id) 元组, 必须解包
            agent, _ = get_graph_executor(checkpointer=saver)
            state_snapshot = await agent.aget_state({"configurable": {"thread_id": session_id}})
            if state_snapshot and getattr(state_snapshot, "values", None):
                events = state_snapshot.values.get("timeline_events", [])
                return {"session_id": session_id, "events": list(events)}
            return {"session_id": session_id, "events": []}
    except Exception as e:
        logger.error(f"Error fetching timeline: {e}")
        return {"session_id": session_id, "events": [], "error": str(e)}


@router.get("/palace/conflicts")
@router.get("/ins-fqz/palace/conflicts")
async def api_get_conflicts():
    """[V4.9.6] 检测当前记忆系统中的逻辑冲突"""
    from app.entity_extractor import _latest_findings
    from app.conflict_detector import detect_conflicts
    return {"conflicts": detect_conflicts(_latest_findings)}


@router.post("/palace/conflicts/resolve")
@router.post("/ins-fqz/palace/conflicts/resolve")
async def api_resolve_conflict(req: ResolveRequest):
    """[V4.9.6] 用户手动解决证据冲突"""
    from app.conflict_detector import mark_resolved
    mark_resolved(req.finding_a, req.keep_a)
    mark_resolved(req.finding_b, req.keep_b)
    return {"status": "success", "message": "冲突已解决"}
