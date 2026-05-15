"""
app/core/task_pool.py
=====================
[V173.0] 动态任务池 (HITL Task Pool Manager)

职责：
1. 存储待人类审批的审计任务状态。
2. 管理任务的生命周期（PENDING -> APPROVED/REJECTED）。
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

class TaskPoolManager:
    def __init__(self):
        # 注意：此处使用内存存储作为演示，生产环境应持久化至 Redis 或 Postgres
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}

    def submit_task(self, thread_id: str, state: Dict[str, Any], reason: str):
        """
        将 Agent 状态提交至任务池，并进入休眠等待
        """
        self._pending_tasks[thread_id] = {
            "thread_id": thread_id,
            "submitted_at": datetime.now().isoformat(),
            "status": "PENDING",
            "reason": reason,
            "user_question": state.get("metadata", {}).get("user_question", "未知审计需求"),
            "risk_score": (state.get("metadata") or {}).get("risk_score", 0.0),
            # 快照仅存储关键数据，避免内存溢出
            "summary": f"当前发现: {len(state.get('audit_findings', []))} 条违规迹象"
        }
        logger.info(f"📥 [TaskPool] 收到高风险审计任务，已挂起等待专家审批: {thread_id}")

    def get_task(self, thread_id: str) -> Optional[Dict]:
        return self._pending_tasks.get(thread_id)

    def list_all_pending(self) -> List[Dict]:
        """供前端管理后台调用的接口"""
        return [t for t in self._pending_tasks.values() if t["status"] == "PENDING"]

    def complete_task(self, thread_id: str, action: str, feedback: str = ""):
        """
        人类完成审批动作
        action: 'APPROVE' | 'REJECT' | 'REVISE'
        """
        if thread_id in self._pending_tasks:
            self._pending_tasks[thread_id]["status"] = "COMPLETED"
            self._pending_tasks[thread_id]["action"] = action
            self._pending_tasks[thread_id]["feedback"] = feedback
            self._pending_tasks[thread_id]["completed_at"] = datetime.now().isoformat()
            logger.success(f"⚖️ [TaskPool] 人类专家已完成审计任务 [{thread_id}] 的审批: {action}")

# 全局单例
task_pool = TaskPoolManager()
