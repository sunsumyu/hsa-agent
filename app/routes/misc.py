"""
app/routes/misc.py
==================
独立小路由集合: models / history / metrics / trace.
从 main.py 提取，保持 API 路径不变。
"""

from fastapi import APIRouter, Request
from loguru import logger

from app.model_manager import model_manager
from app.history import history_manager
from app.usage_tracker import usage_tracker

router = APIRouter()


@router.get("/agent/models")
@router.get("/ins-fqz/agent/models")
async def get_models():
    """获取可用模型列表"""
    return model_manager.get_model_list()


@router.post("/agent/models/probe")
@router.post("/ins-fqz/agent/models/probe")
async def probe_models():
    """[V5.3.0] 触发全量算力体检"""
    report = await model_manager.run_health_check()
    return report


@router.get("/agent/history")
@router.get("/ins-fqz/agent/history")
async def get_history(request: Request):
    """获取指定会话的历史记录 (禁用自动恢复，确保物理隔离)"""
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    # [V15.9.1] 彻底修复：禁用 auto_recover。如果 session_id 是未见过的，后端必须返回空历史
    # 而不是擅自通过读取 data/history 下的最早文件来污染新会话
    history = history_manager.get_history(session_id, auto_recover=False)
    # [V15.6] 生产级 API：显式过滤历史消息，仅公开人类与 AI 回复，屏蔽中间思维包与系统指令
    return [
        {"role": "user" if msg.type == "human" else "ai", "content": msg.content}
        for msg in history if msg.type in ["human", "ai", "assistant"]
    ]


@router.get("/agent/metrics")
@router.get("/ins-fqz/agent/metrics")
async def get_metrics():
    """[V4.8.0] 可视化工具链：返回实时 Token 消耗、模型用量和成本统计"""
    from app.usage_tracker import usage_tracker

    stats = usage_tracker.stats
    daily = stats.daily_usage
    total = stats.total_usage

    current_min = usage_tracker._get_current_minute()

    # 读取各模型的配额与成本配置
    models_detail = []
    for model_id, cfg in usage_tracker.model_configs.items():
        current = daily.get(model_id, 0)
        rpd = usage_tracker.stats.daily_requests.get(model_id, 0)
        rpm = usage_tracker.rpm_window.get(model_id, {}).get(current_min, 0)
        tpm = usage_tracker.tpm_window.get(model_id, {}).get(current_min, 0)

        quota = cfg.daily_quota
        i_cost_rate = cfg.input_cost_1k
        o_cost_rate = cfg.output_cost_1k
        # 估算日成本 (简化：假设 input:output = 3:1)
        est_cost = (current / 1000) * (i_cost_rate * 0.75 + o_cost_rate * 0.25)

        models_detail.append({
            "id": model_id,
            "name": cfg.model_name,
            "provider": cfg.provider,
            "daily_used": current,
            "daily_quota": quota,
            "daily_requests": rpd,
            "rpd_limit": cfg.rpd_limit,
            "current_rpm": rpm,
            "rpm_limit": cfg.rpm_limit,
            "current_tpm": tpm,
            "tpm_limit": cfg.tpm_limit,
            "usage_pct": round(current / max(quota, 1) * 100, 1),
            "estimated_cost": round(est_cost, 4),
            "lifetime_tokens": total.get(model_id, 0)
        })

    return {
        "date": stats.today,
        "current_minute": current_min,
        "models": models_detail,
        "total_daily_tokens": sum(daily.values()),
        "total_lifetime_tokens": sum(total.values()),
        "total_daily_requests": sum(usage_tracker.stats.daily_requests.values())
    }


@router.get("/agent/trace")
@router.get("/ins-fqz/agent/trace")
async def get_trace():
    """[V4.8.0] 可视化工具链：返回最近一次推演的节点执行轨迹"""
    # 诊断轨迹已迁移至 Phoenix OpenTelemetry
    return {"status": "deprecated", "message": "Diagnostic tracing is now handled by Phoenix OpenTelemetry. Please visit the Phoenix UI."}
