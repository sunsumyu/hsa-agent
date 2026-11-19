"""
app/core/graph_state_orchestrator.py
====================================
图执行器状态治理与会话生命周期编排器 (Deep Module)

核心职责：
1. 会话状态快照与时间轴证据安全提取
2. 人工干预线索覆盖格式化 (⟦OVERWRITE⟧) 与状态注入
3. 多线程会话分叉克隆 (Fork/A-B Testing) 与隔离复制
4. 检查点持久化生命周期兼容保护
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from loguru import logger


def format_findings_overwrite(findings: Any) -> List[str]:
    """将输入的线索列表或文本标准化包装为带 ⟦OVERWRITE⟧ 标识的指令结构。"""
    if isinstance(findings, list):
        return ["⟦OVERWRITE⟧" + "\n".join(str(f) for f in findings)]
    return ["⟦OVERWRITE⟧" + str(findings)]


async def get_session_timeline_events(
    session_id: str,
    checkpointer: Optional[Any] = None,
    executor: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """安全提取指定会话的历史离散推演时间轴切片。"""
    try:
        if executor is not None:
            exec_instance = executor
            config = {"configurable": {"thread_id": session_id}}
            state_snapshot = await exec_instance.aget_state(config)
            if state_snapshot and getattr(state_snapshot, "values", None):
                events = state_snapshot.values.get("timeline_events", [])
                return list(events)
            return []

        from app.core.agent_graph import get_graph_executor
        if checkpointer is None:
            try:
                from app.core.checkpointer import create_checkpointer
                async with create_checkpointer() as fallback_saver:
                    exec_instance, _ = get_graph_executor(checkpointer=fallback_saver)
                    config = {"configurable": {"thread_id": session_id}}
                    state_snapshot = await exec_instance.aget_state(config)
                    if state_snapshot and getattr(state_snapshot, "values", None):
                        events = state_snapshot.values.get("timeline_events", [])
                        return list(events)
                    return []
            except Exception as e:
                logger.debug(f"[GraphStateOrchestrator] Fallback checkpoint access skipped: {e}")

        exec_instance, _ = get_graph_executor(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": session_id}}
        state_snapshot = await exec_instance.aget_state(config)
        if state_snapshot and getattr(state_snapshot, "values", None):
            events = state_snapshot.values.get("timeline_events", [])
            return list(events)
        return []
    except Exception as e:
        logger.error(f"[GraphStateOrchestrator] 获取时间轴事件失败 (session={session_id}): {e}")
        return []


async def intervene_session_findings(
    session_id: str,
    findings: Any,
    checkpointer: Optional[Any] = None,
    executor: Optional[Any] = None,
) -> Dict[str, Any]:
    """人工干预指定会话的推演线索，注入 ⟦OVERWRITE⟧ 指令以在后续轮次生效。"""
    try:
        if executor is None:
            from app.core.agent_graph import get_graph_executor
            exec_instance, _ = get_graph_executor(checkpointer=checkpointer)
        else:
            exec_instance = executor

        config = {"configurable": {"thread_id": session_id}}
        current_state = await exec_instance.aget_state(config)
        if not current_state or not getattr(current_state, "values", None):
            return {"status": "error", "message": "会话不存在或未初始化"}

        new_findings = format_findings_overwrite(findings)
        await exec_instance.aupdate_state(config, {"findings": new_findings})
        logger.warning(f">>> [人工干预] Session {session_id} 的线索库已被手动覆盖")
        return {"status": "success", "message": "状态已更新，下次推演将使用新线索"}
    except Exception as e:
        logger.error(f"[GraphStateOrchestrator] 会话人工干预失败 (session={session_id}): {e}")
        return {"status": "error", "message": str(e)}


async def fork_session_thread(
    source_session: str,
    target_session: str,
    checkpointer: Optional[Any] = None,
    executor: Optional[Any] = None,
) -> Dict[str, Any]:
    """将源会话的图状态完整克隆到目标会话线程，用于分支探索或对比回放。"""
    try:
        if executor is None:
            from app.core.agent_graph import get_graph_executor
            exec_instance, _ = get_graph_executor(checkpointer=checkpointer)
        else:
            exec_instance = executor

        source_config = {"configurable": {"thread_id": source_session}}
        target_config = {"configurable": {"thread_id": target_session}}

        state = await exec_instance.aget_state(source_config)
        if not state or not getattr(state, "values", None):
            return {"status": "error", "message": "源会话不存在"}

        await exec_instance.aupdate_state(target_config, state.values)
        logger.info(f">>> [会话分叉] 从 {source_session} 克隆至 {target_session}")
        return {"status": "success", "targetSession": target_session}
    except Exception as e:
        logger.error(f"[GraphStateOrchestrator] 会话分叉失败 ({source_session} -> {target_session}): {e}")
        return {"status": "error", "message": str(e)}


class GraphStateOrchestrator:
    """图状态治理与会话生命周期编排器。"""

    def __init__(self, checkpointer: Optional[Any] = None):
        self._checkpointer = checkpointer

    async def get_timeline_events(self, session_id: str, checkpointer: Optional[Any] = None) -> List[Dict[str, Any]]:
        cp = checkpointer or self._checkpointer
        return await get_session_timeline_events(session_id, checkpointer=cp)

    async def intervene_findings(self, session_id: str, findings: Any, checkpointer: Optional[Any] = None) -> Dict[str, Any]:
        cp = checkpointer or self._checkpointer
        return await intervene_session_findings(session_id, findings, checkpointer=cp)

    async def fork_session(self, source_session: str, target_session: str, checkpointer: Optional[Any] = None) -> Dict[str, Any]:
        cp = checkpointer or self._checkpointer
        return await fork_session_thread(source_session, target_session, checkpointer=cp)


# 全局默认单例
graph_state_orchestrator = GraphStateOrchestrator()
