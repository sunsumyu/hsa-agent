import json
import pytest
from unittest.mock import MagicMock
from app.core.task_pool import TaskPoolManager

class FakeRedisHashClient:
    """模拟 Redis Hash 操作支持的客户端"""
    def __init__(self):
        self.hashes = {}
        self.store = {}

    def hset(self, name, key, value):
        if name not in self.hashes:
            self.hashes[name] = {}
        self.hashes[name][str(key)] = str(value)
        return 1

    def hget(self, name, key):
        return self.hashes.get(name, {}).get(str(key))

    def hdel(self, name, *keys):
        count = 0
        if name in self.hashes:
            for k in keys:
                if str(k) in self.hashes[name]:
                    del self.hashes[name][str(k)]
                    count += 1
        return count

    def hvals(self, name):
        return list(self.hashes.get(name, {}).values())


def test_task_pool_submits_and_completes_in_redis():
    """RED 测试：在 Redis 可用时，任务必须持久化至 Redis Hash，且完成时原子转移到 completed"""
    fake_redis = FakeRedisHashClient()
    mock_redis_manager = MagicMock()
    mock_redis_manager.is_connected = True
    mock_redis_manager.client = fake_redis

    from contextlib import contextmanager
    @contextmanager
    def fake_lock(key, timeout=10):
        yield True
    mock_redis_manager.dist_lock = fake_lock

    pool = TaskPoolManager(redis_client=mock_redis_manager)

    thread_id = "test_audit_task_001"
    state = {
        "metadata": {"user_question": "排查异地就医", "risk_score": 0.88},
        "audit_findings": ["发现异常就医 3 笔"]
    }

    # 1. 提交任务
    pool.submit_task(thread_id, state, reason="异地异常比对")

    # 必须写入 Redis Hash
    assert fake_redis.hget("argus:task_pool:pending", thread_id) is not None
    pending = pool.list_all_pending()
    assert len(pending) == 1
    assert pending[0]["thread_id"] == thread_id
    assert pending[0]["status"] == "PENDING"

    # 2. 审批完成任务
    success = pool.complete_task(thread_id, action="APPROVE", feedback="准予放行")
    assert success is True

    # 验证 pending 已移除，completed 已写入
    assert fake_redis.hget("argus:task_pool:pending", thread_id) is None
    assert fake_redis.hget("argus:task_pool:completed", thread_id) is not None

    # 查询任务应能查到 completed 数据
    task = pool.get_task(thread_id)
    assert task is not None
    assert task["status"] == "COMPLETED"
    assert task["action"] == "APPROVE"
    assert task["feedback"] == "准予放行"
    assert "completed_at" in task


def test_task_pool_complete_task_is_idempotent():
    """RED 测试：审批必须具备幂等性与 CAS 保护，已完成的任务严禁被二次覆盖"""
    fake_redis = FakeRedisHashClient()
    mock_redis_manager = MagicMock()
    mock_redis_manager.is_connected = True
    mock_redis_manager.client = fake_redis

    from contextlib import contextmanager
    @contextmanager
    def fake_lock(key, timeout=10):
        yield True
    mock_redis_manager.dist_lock = fake_lock

    pool = TaskPoolManager(redis_client=mock_redis_manager)
    thread_id = "test_idempotent_task"
    pool.submit_task(thread_id, {"metadata": {}}, reason="待核验")

    # 第一次审批：APPROVE
    res1 = pool.complete_task(thread_id, action="APPROVE", feedback="首次通过")
    assert res1 is True
    first_completed_at = pool.get_task(thread_id)["completed_at"]

    # 第二次重复审批（例如网络抖动或不同审核员并发提交）：REJECT
    res2 = pool.complete_task(thread_id, action="REJECT", feedback="恶意篡改驳回")
    # 幂等断言：状态依然为首次审批结果，且时间戳未被篡改
    task = pool.get_task(thread_id)
    assert task["status"] == "COMPLETED"
    assert task["action"] == "APPROVE"
    assert task["feedback"] == "首次通过"
    assert task["completed_at"] == first_completed_at
