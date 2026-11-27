"""
app/routes/misc.py
==================
独立小路由集合: models / history / metrics / trace.
从 main.py 提取，保持 API 路径不变。
各端点底层委托至相应深模块 (model_manager, history_manager, usage_tracker)。
"""

from fastapi import APIRouter, Request
from loguru import logger

from app.infra.model_manager import model_manager
from app.core.memory.history import history_manager
from app.infra.usage_tracker import usage_tracker
from app.api.envelope import ResponseEnvelope

router = APIRouter()


@router.get("/agent/models")
@router.get("/ins-fqz/agent/models")
async def get_models():
    """获取可用模型列表 (注入法律辩法智能体)"""
    models = model_manager.get_model_list()
    legal_agent_meta = {
        "id": "legal-agent",
        "name": "⚖️ 法律辩法智能体 (三段论与红蓝对抗)",
        "provider": "Argus-Legal",
        "tools_support": True,
        "priority": 999,
        "is_available": True,
        "status_msg": "就绪 (时效刚性计算/4倍LPR/自相矛盾审查)",
    }
    return [legal_agent_meta] + [m for m in models if m.get("id") != "legal-agent"]


@router.post("/agent/models/probe")
@router.post("/ins-fqz/agent/models/probe")
async def probe_models():
    """触发全量算力体检与云端探针自检"""
    await model_manager.probe_all_endpoints()
    return ResponseEnvelope.success(message="全量自检与云端额度同步完成")


@router.get("/agent/history")
@router.get("/ins-fqz/agent/history")
async def get_history(request: Request):
    """获取指定会话的历史记录 (禁用自动恢复，确保物理隔离)"""
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    history = history_manager.get_history(session_id, auto_recover=False)
    # 生产级 API：显式过滤历史消息，仅公开人类与 AI 回复，屏蔽中间思维包与系统指令
    return [
        {"role": "user" if msg.type == "human" else "ai", "content": msg.content}
        for msg in history if msg.type in ["human", "ai", "assistant"]
    ]


@router.get("/agent/statistics")
@router.get("/agent/metrics")
@router.get("/ins-fqz/agent/statistics")
@router.get("/ins-fqz/agent/metrics")
async def get_metrics():
    """[V4.8.0] 可视化工具链：返回实时 Token 消耗、模型用量和成本统计"""
    return usage_tracker.get_realtime_metrics()


@router.get("/agent/trajectory")
@router.get("/agent/trace")
@router.get("/ins-fqz/agent/trajectory")
@router.get("/ins-fqz/agent/trace")
async def get_trace():
    """[V4.8.0] 可视化工具链：返回最近一次推演的节点执行轨迹"""
    # 诊断轨迹已迁移至 Phoenix OpenTelemetry
    return ResponseEnvelope.success(
        status="deprecated",
        message="Diagnostic tracing is now handled by Phoenix OpenTelemetry. Please visit the Phoenix UI."
    )
