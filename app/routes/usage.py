"""
app/routes/usage.py
====================
[V4.6] 算力消耗与 Token 治理 API
对接 UsageTracker 实时数据，为前端门户提供真实消耗数据
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/api/usage", tags=["Usage & Token Governance"])

@router.get("/stats")
async def get_usage_stats():
    """
    [V4.6] 实时算力消耗数据
    返回所有节点的今日 Token 消耗、请求数、健康分及计费估算
    """
    try:
        from app.usage_tracker import usage_tracker
        from datetime import datetime

        tracker = usage_tracker
        nodes = []
        total_tokens = 0
        total_cost = 0.0

        # 遍历所有已知的模型节点
        for model_id, cfg in tracker.model_configs.items():
            daily_tokens = tracker.stats.daily_usage.get(model_id, 0)
            daily_requests = tracker.stats.daily_requests.get(model_id, 0)
            total_tokens_all = tracker.stats.total_usage.get(model_id, 0)
            stability = tracker.get_stability_score(model_id)
            avg_latency = tracker.get_avg_latency(model_id)

            # 今日计费估算
            i_tokens = int(daily_tokens * 0.6)  # 估算 input 占比
            o_tokens = daily_tokens - i_tokens
            cost = (i_tokens / 1000) * cfg.input_cost_1k + (o_tokens / 1000) * cfg.output_cost_1k

            # 黑名单状态
            import time
            is_blacklisted = not cfg.is_active or (
                model_id in tracker.blacklist_expiry and time.time() < tracker.blacklist_expiry.get(model_id, 0)
            )

            status = "BLACKLISTED" if is_blacklisted else ("ACTIVE" if daily_requests > 0 else "STANDBY")

            nodes.append({
                "id": model_id,
                "provider": _guess_provider(model_id),
                "tier": cfg.priority if hasattr(cfg, "priority") else 1,
                "status": status,
                "daily_tokens": daily_tokens,
                "daily_requests": daily_requests,
                "total_tokens": total_tokens_all,
                "daily_quota": cfg.daily_quota,
                "quota_pct": round(daily_tokens / cfg.daily_quota * 100, 1) if cfg.daily_quota else 0,
                "cost_usd": round(cost, 4),
                "stability": round(stability * 100),
                "avg_latency_ms": round(avg_latency),
                "burnout_rounds": tracker.get_burnout_prediction(model_id),
                "last_error": cfg.last_error
            })
            total_tokens += daily_tokens
            total_cost += cost

        # 按今日 Token 消耗倒序
        nodes.sort(key=lambda x: x["daily_tokens"], reverse=True)

        return JSONResponse(content={
            "ok": True,
            "data": {
                "timestamp": datetime.now().isoformat(),
                "today": tracker.stats.today,
                "total_daily_tokens": total_tokens,
                "total_daily_cost_usd": round(total_cost, 4),
                "active_nodes": sum(1 for n in nodes if n["status"] == "ACTIVE"),
                "blacklisted_nodes": sum(1 for n in nodes if n["status"] == "BLACKLISTED"),
                "nodes": nodes
            }
        })
    except Exception as e:
        logger.error(f"❌ [UsageAPI] 数据采集失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.post("/reset-blacklists")
async def reset_blacklists():
    """[V4.6] 紧急恢复：清除所有黑名单，重启算力链路"""
    try:
        from app.usage_tracker import usage_tracker
        usage_tracker.reset_blacklists()
        return JSONResponse(content={"ok": True, "message": "全量黑名单已清除，所有节点重新就绪"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


def _guess_provider(model_id: str) -> str:
    """根据模型 ID 推断供应商名称"""
    mid = model_id.lower()
    if "qwen" in mid or "bailian" in mid or "aliyun" in mid or "dashscope" in mid:
        return "阿里云百炼"
    if "doubao" in mid or "volcano" in mid or "ark" in mid or "ep-" in mid:
        return "火山引擎"
    if "deepseek" in mid:
        return "DeepSeek"
    if "gpt" in mid or "azure" in mid or "openai" in mid:
        return "Azure/OpenAI"
    if "gemini" in mid or "google" in mid:
        return "Google"
    if "claude" in mid or "anthropic" in mid:
        return "Anthropic"
    return "Unknown"
