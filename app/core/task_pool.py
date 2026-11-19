"""
app/core/task_pool.py
=====================
[V173.1] 动态任务池 (HITL Task Pool Manager) - 分布式持久化与 CAS 幂等状态机

职责：
1. 存储待人类审批的审计任务状态（支持 Redis Hash 分布式共享与本地线程安全内存降级）。
2. 管理任务的生命周期（PENDING -> APPROVED/REJECTED）。
3. 保证多审核员并发场景下的分布式互斥与审批幂等性（CAS 防二次覆盖）。
"""

import json
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger


class TaskPoolManager:
    """[V173.1] 企业级分布式 HITL 任务池管理器"""

    PENDING_KEY = "argus:task_pool:pending"
    COMPLETED_KEY = "argus:task_pool:completed"

    def __init__(self, redis_client: Optional[Any] = None):
        if redis_client is not None:
            self.redis_client = redis_client
        else:
            from app.infra.redis_client import redis_manager
            self.redis_client = redis_manager

        # 本地内存降级存储与并发锁 (当 Redis 不可用时自动启用)
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}
        self._completed_tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _is_redis_active(self) -> bool:
        return bool(
            self.redis_client
            and getattr(self.redis_client, "is_connected", False)
            and getattr(self.redis_client, "client", None)
        )

    def submit_task(self, thread_id: str, state: Dict[str, Any], reason: str):
        """
        将 Agent 状态提交至任务池，并进入休眠等待专家审批
        """
        meta = state.get("metadata") or {}
        findings = state.get("audit_findings") or []

        task_data = {
            "thread_id": thread_id,
            "submitted_at": datetime.now().isoformat(),
            "status": "PENDING",
            "reason": reason,
            "user_question": meta.get("user_question", "未知审计需求"),
            "risk_score": meta.get("risk_score", 0.0),
            # 快照仅存储关键数据，避免内存/网络载荷溢出
            "summary": f"当前发现: {len(findings)} 条违规迹象"
        }

        if self._is_redis_active():
            try:
                self.redis_client.client.hset(
                    self.PENDING_KEY,
                    thread_id,
                    json.dumps(task_data, ensure_ascii=False)
                )
                logger.info(f"📥 [TaskPool] 收到高风险审计任务，已挂起至分布式任务池 (Redis): {thread_id}")
                return
            except Exception as e:
                logger.error(f"❌ [TaskPool] 写入 Redis 异常，降级至本地内存: {e}")

        with self._lock:
            self._pending_tasks[thread_id] = task_data
        logger.info(f"📥 [TaskPool] 收到高风险审计任务，已挂起等待专家审批 (Memory): {thread_id}")

    def get_task(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 thread_id 的任务状态（涵盖 PENDING 与 COMPLETED）"""
        if self._is_redis_active():
            try:
                # 优先查询待审批任务
                raw_pending = self.redis_client.client.hget(self.PENDING_KEY, thread_id)
                if raw_pending:
                    return json.loads(raw_pending)
                # 其次查询已完成任务
                raw_completed = self.redis_client.client.hget(self.COMPLETED_KEY, thread_id)
                if raw_completed:
                    return json.loads(raw_completed)
                return None
            except Exception as e:
                logger.error(f"❌ [TaskPool] 读取 Redis 异常，回退内存查询: {e}")

        with self._lock:
            if thread_id in self._pending_tasks:
                return dict(self._pending_tasks[thread_id])
            if thread_id in self._completed_tasks:
                return dict(self._completed_tasks[thread_id])
            return None

    def list_all_pending(self) -> List[Dict[str, Any]]:
        """供前端管理后台调用的接口：获取所有处于 PENDING 状态的任务"""
        if self._is_redis_active():
            try:
                raw_vals = self.redis_client.client.hvals(self.PENDING_KEY)
                results = []
                for val in raw_vals:
                    try:
                        item = json.loads(val)
                        if item.get("status") == "PENDING":
                            results.append(item)
                    except Exception:
                        continue
                return results
            except Exception as e:
                logger.error(f"❌ [TaskPool] 查询 Redis Pending 列表异常: {e}")

        with self._lock:
            return [dict(t) for t in self._pending_tasks.values() if t["status"] == "PENDING"]

    def complete_task(self, thread_id: str, action: str, feedback: str = "") -> bool:
        """
        人类完成审批动作（具备分布式互斥锁与 CAS 幂等保护）
        action: 'APPROVE' | 'REJECT' | 'REVISE'
        """
        if self._is_redis_active():
            lock_ctx = getattr(self.redis_client, "dist_lock", None)
            from contextlib import nullcontext
            ctx = lock_ctx(f"task:approval:{thread_id}", timeout=10) if lock_ctx else nullcontext(True)

            with ctx as acquired:
                if acquired is False:
                    logger.warning(f"🔒 [TaskPool] 任务 [{thread_id}] 正在被他人审批，请勿并发提交")
                    return False

                try:
                    # 1. 幂等校验：检查是否已经审批完成
                    raw_completed = self.redis_client.client.hget(self.COMPLETED_KEY, thread_id)
                    if raw_completed:
                        logger.warning(f"⚠️ [TaskPool] 任务 [{thread_id}] 已处于完成态，幂等忽略重复审批")
                        return True

                    # 2. 从 Pending 中提取
                    raw_pending = self.redis_client.client.hget(self.PENDING_KEY, thread_id)
                    if not raw_pending:
                        logger.warning(f"⚠️ [TaskPool] 未在 Pending 池中检索到任务 [{thread_id}]")
                        return False

                    task = json.loads(raw_pending)
                    task["status"] = "COMPLETED"
                    task["action"] = action
                    task["feedback"] = feedback
                    task["completed_at"] = datetime.now().isoformat()

                    # 3. 原子转移：写入 Completed，移出 Pending
                    self.redis_client.client.hset(
                        self.COMPLETED_KEY,
                        thread_id,
                        json.dumps(task, ensure_ascii=False)
                    )
                    self.redis_client.client.hdel(self.PENDING_KEY, thread_id)
                    logger.success(f"⚖️ [TaskPool] 分布式审批已完成 [{thread_id}]: {action}")
                    return True
                except Exception as e:
                    logger.error(f"❌ [TaskPool] 完成审批写入 Redis 异常: {e}")

        # 内存模式降级处理
        with self._lock:
            if thread_id in self._completed_tasks:
                logger.warning(f"⚠️ [TaskPool] 任务 [{thread_id}] 内存中已处于完成态，幂等忽略重复审批")
                return True

            if thread_id in self._pending_tasks:
                task = self._pending_tasks.pop(thread_id)
                task["status"] = "COMPLETED"
                task["action"] = action
                task["feedback"] = feedback
                task["completed_at"] = datetime.now().isoformat()
                self._completed_tasks[thread_id] = task
                logger.success(f"⚖️ [TaskPool] 本地内存审批已完成 [{thread_id}]: {action}")
                return True

            return False


# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

task_pool = LazyProxy("task_pool")
