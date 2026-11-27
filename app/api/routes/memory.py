"""
app/routes/memory.py
====================
[V4.6] 记忆中枢监控 API
薄控制器设计，提供实时记忆架构健康信标、摘要与三维淘汰 GC 接口。
接入统一 ResponseEnvelope，标准化响应信封与错误拦截。
"""

from fastapi import APIRouter
from loguru import logger
from app.api.envelope import ResponseEnvelope

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
        return ResponseEnvelope.success(data=stats)
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 健康信标采集失败: {e}")
        return ResponseEnvelope.error(error=str(e), status_code=500)


@router.get("/summary")
async def get_memory_summary():
    """
    [V4.6] 记忆中枢简要摘要 (供 Agent Prompt 注入)
    """
    try:
        from app.core.memory.manager import memory_hub
        return ResponseEnvelope.success(summary=memory_hub.get_summary())
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 摘要生成失败: {e}")
        return ResponseEnvelope.error(error=str(e), status_code=500)


def validate_forget_params(strategy: str, threshold: float, max_age_days: int) -> None:
    """校验遗忘引擎参数合法性契约"""
    if strategy not in ("combined", "importance_based", "time_based"):
        raise ValueError(f"不支持的遗忘淘汰策略: {strategy}，可选策略为: combined, importance_based, time_based")
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"重要性阈值 threshold 必须在 [0.0, 1.0] 范围内，当前为: {threshold}")
    if max_age_days <= 0:
        raise ValueError(f"最大存活天数 max_age_days 必须大于等于 1，当前为: {max_age_days}")


@router.post("/forget")
async def trigger_forget(strategy: str = "combined", threshold: float = 0.2, max_age_days: int = 30):
    """
    [V4.6] 触发三维淘汰引擎
    可从门户手动触发，执行 GC 清理
    """
    try:
        validate_forget_params(strategy, threshold, max_age_days)
        from app.core.memory.manager import memory_hub
        report = await memory_hub.forget_memories(
            strategy=strategy,
            threshold=threshold,
            max_age_days=max_age_days
        )
        return ResponseEnvelope.success(report=report)
    except ValueError as ve:
        logger.warning(f"⚠️ [MemoryAPI] 遗忘引擎参数校验失败: {ve}")
        return ResponseEnvelope.error(error=str(ve), status_code=400)
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 遗忘引擎触发失败: {e}")
        return ResponseEnvelope.error(error=str(e), status_code=500)


@router.get("/cache-stats")
async def get_cache_and_experience_stats():
    """
    返回动作语义缓存 (action_cache) 与黄金经验池 (pool.json) 的命中次数与命中率统计。
    """
    try:
        from app.core.memory.action_cache import action_cache_manager
        from app.core.memory.experience import experience_manager
        return ResponseEnvelope.success(
            data={
                "action_cache": action_cache_manager.get_stats(),
                "experience_pool": experience_manager.get_stats(),
            }
        )
    except Exception as e:
        logger.error(f"❌ [MemoryAPI] 缓存统计采集失败: {e}")
        return ResponseEnvelope.error(error=str(e), status_code=500)
