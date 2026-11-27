"""
app/routes/usage.py
===================
[V4.6] 算力消耗与 Token 治理 API
对接 UsageTracker 实时数据，为前端门户提供真实消耗与治理数据。
业务计算与治理快照完全封装在 UsageTracker 深模块内。
接入统一 ResponseEnvelope，异常交由全局中间件拦截。
"""

from fastapi import APIRouter
from loguru import logger
from app.infra.usage_tracker import usage_tracker, UsageTracker
from app.api.envelope import ResponseEnvelope

router = APIRouter(prefix="/api/usage", tags=["Usage & Token Governance"])


@router.get("/stats")
async def get_usage_stats():
    """
    [V4.6] 实时算力消耗数据
    返回所有节点的今日 Token 消耗、请求数、健康分及计费估算
    """
    snapshot = usage_tracker.get_governance_snapshot()
    return ResponseEnvelope.success(data=snapshot)


@router.post("/reset-blacklists")
async def reset_blacklists():
    """[V4.6] 紧急恢复：清除所有黑名单，重启算力链路"""
    usage_tracker.reset_blacklists()
    return ResponseEnvelope.success(message="全量黑名单已清除，所有节点重新就绪")


# 向后兼容导出
_guess_provider = getattr(UsageTracker, "infer_provider", None) or (lambda m: "Unknown")
