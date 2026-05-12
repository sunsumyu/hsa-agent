"""
app/routes/graph_state.py
=========================
图状态管理路由: update_state / fork_session.
"""

from fastapi import APIRouter, Request
from loguru import logger

from app.agent_graph import get_graph_executor

router = APIRouter()


@router.post("/agent/update_state")
@router.post("/ins-fqz/agent/update_state")
async def update_state(request: Request):
    """人工干预接口：修改指定会话的中间状态 (Debug Mode)"""
    data = await request.json()
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    findings = data.get("findings")  # 期望修改后的线索列表

    executor, _ = get_graph_executor(checkpointer=request.app.state.saver)
    config = {"configurable": {"thread_id": session_id}}

    # 获取当前状态
    current_state = await executor.aget_state(config)
    if not current_state.values:
        return {"status": "error", "message": "会话不存在或未初始化"}

    # 注入覆盖指令 ⟦OVERWRITE⟧
    new_findings = ["⟦OVERWRITE⟧" + "\n".join(findings)] if isinstance(findings, list) else ["⟦OVERWRITE⟧" + str(findings)]

    await executor.aupdate_state(config, {"findings": new_findings})
    logger.warning(f">>> [人工干预] Session {session_id} 的线索库已被手动覆盖")
    return {"status": "success", "message": "状态已更新，下次推演将使用新线索"}


@router.post("/agent/fork")
@router.post("/ins-fqz/agent/fork")
async def fork_session(request: Request):
    """会话分叉接口：克隆当前会话到新 Thread (A/B Test)"""
    data = await request.json()
    source_session = data.get("sourceSessionId")
    target_session = data.get("targetSessionId")

    executor, _ = get_graph_executor(checkpointer=request.app.state.saver)
    source_config = {"configurable": {"thread_id": source_session}}
    target_config = {"configurable": {"thread_id": target_session}}

    state = await executor.aget_state(source_config)
    if not state.values:
        return {"status": "error", "message": "源会话不存在"}

    await executor.aupdate_state(target_config, state.values)
    logger.info(f">>> [会话分叉] 从 {source_session} 克隆至 {target_session}")
    return {"status": "success", "targetSession": target_session}
