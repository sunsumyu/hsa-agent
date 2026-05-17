"""
app/routes/memory.py
====================
[V4.6] 记忆中枢监控 API
提供实时记忆架构健康信标与运营数据端点
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/api/memory", tags=["Memory Hub"])

@router.get("/stats")
async def get_memory_stats():
    """
    [V4.6] 记忆中枢健康信标
    返回 L0-L3 四层记忆的实时状态与基础设施信息
    """
    try:
        from app.core.memory.manager import memory_hub
        stats = memory_hub.get_stats()
        return JSONResponse(content={"ok": True, "data": stats})
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 健康信标采集失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

@router.get("/summary")
async def get_memory_summary():
    """
    [V4.6] 记忆中枢简要摘要 (供 Agent Prompt 注入)
    """
    try:
        from app.core.memory.manager import memory_hub
        return JSONResponse(content={"ok": True, "summary": memory_hub.get_summary()})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.post("/forget")
async def trigger_forget(strategy: str = "combined", threshold: float = 0.2, max_age_days: int = 30):
    """
    [V4.6] 触发三维淘汰引擎
    可从门户手动触发，执行 GC 清理
    """
    try:
        from app.core.memory.manager import memory_hub
        report = await memory_hub.forget_memories(
            strategy=strategy,
            threshold=threshold,
            max_age_days=max_age_days
        )
        return JSONResponse(content={"ok": True, "report": report})
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 遗忘引擎触发失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
