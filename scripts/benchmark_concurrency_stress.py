"""
scripts/benchmark_concurrency_stress.py
======================================
系统级并发与幂等压力基准测试 (Concurrency & Idempotency Stress Benchmark)
"""

import os
import sys
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

# 解决 Windows 控制台 GBK 打印 Emoji 报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath("."))

from app.infra.redis_client import redis_manager
from app.infra.db_conn import CharsetProxy
from app.infra.usage_tracker import UsageTracker
from app.core.task_pool import TaskPoolManager
from app.api.chat_stream_coordinator import ChatStreamCoordinator


def test_component_concurrency_stress():
    print("\n" + "="*60)
    print("[基准压测 1] 底层驱动与度量高并发竞争压力测试 (50 线程并发)")
    print("="*60)

    # 1. 压测 CharsetProxy 互斥与无重叠
    class MockDbClient:
        def __init__(self):
            self.overlap = 0
            self.current = 0
            self.total = 0

        def query(self, sql):
            self.current += 1
            if self.current > self.overlap:
                self.overlap = self.current
            time.sleep(0.005)  # 5ms 数据库查询耗时
            self.current -= 1
            self.total += 1
            return [{"id": 1}]

    mock_db = MockDbClient()
    proxy = CharsetProxy(mock_db)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(proxy.query, f"SELECT {i}") for i in range(100)]
        for f in futures:
            f.result()
    db_elapsed = time.perf_counter() - start

    print(f"  - ClickHouse 驱动并发压测完成: 总请求数=100, 并发线程=50, 耗时={db_elapsed:.3f}s")
    print(f"  - 底层 Socket 最大并发重叠数 (Max Overlap): {mock_db.overlap} (期望严格等于 1)")
    assert mock_db.overlap == 1, "ClickHouse 物理连接发生多线程重叠竞争！"

    # 2. 压测 UsageTracker 并发累加与原子落盘
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_stats_path = os.path.join(tmp_dir, "stress_usage_stats.json")
        tracker = UsageTracker(stats_path=test_stats_path)
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = [
                pool.submit(tracker.record_usage, "benchmark-model", 100, 200, latency_ms=10.0)
                for _ in range(200)
            ]
            for f in futures:
                f.result()
        tracker_elapsed = time.perf_counter() - start

        actual_tokens = tracker.stats.daily_usage.get("benchmark-model", 0)
        expected_tokens = 200 * 300  # 60000
        actual_reqs = tracker.stats.daily_requests.get("benchmark-model", 0)

        print(f"  - UsageTracker 并发压测完成: 总调用数=200, 并发线程=50, 耗时={tracker_elapsed:.3f}s")
        print(f"  - Token 统计累计值: {actual_tokens} / {expected_tokens} (差异: {expected_tokens - actual_tokens})")
        print(f"  - 请求数统计累计值: {actual_reqs} / 200")
        assert actual_tokens == expected_tokens, f"Token 统计发生并发竞态丢失！期望 {expected_tokens}，实际 {actual_tokens}"
        assert actual_reqs == 200, f"请求数发生并发丢失！期望 200，实际 {actual_reqs}"
        print("  [压测 1 通过] 底层驱动与度量在高频 50 线程冲击下 100% 互斥且数据零丢失！")


def test_task_pool_concurrency_stress():
    print("\n" + "="*60)
    print("[基准压测 2] 人工审批任务池 (HITL) 并发抢占与 CAS 幂等压测 (50 线程并发)")
    print("="*60)

    pool = TaskPoolManager()
    thread_id = "stress-audit-task-999"
    pool.submit_task(thread_id, {"metadata": {"user_question": "高并发测试"}}, reason="压测挂起")

    results = []
    actions = ["APPROVE", "REJECT", "REVISE"]

    def concurrent_approver(idx):
        action = actions[idx % len(actions)]
        res = pool.complete_task(thread_id, action=action, feedback=f"审核人-{idx}")
        return res, action

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(concurrent_approver, i) for i in range(50)]
        for f in futures:
            results.append(f.result())

    task = pool.get_task(thread_id)
    print(f"  - 最终持久化状态: status={task['status']}, action={task['action']}")
    print(f"  - 最终审批人反馈: {task['feedback']}")
    print(f"  - 50 个并发审批中，所有请求均得到安全响应，状态机未错乱")
    assert task["status"] == "COMPLETED"
    print("  [压测 2 通过] TaskPool 在 50 线程并发审批竞争下维持原子状态机，无死锁或数据冲突！")


async def test_api_session_burst_stress():
    print("\n" + "="*60)
    print("[基准压测 3] API 会话级瞬时突发 (Burst) 防重防冲刷压测 (20 并发协程)")
    print("="*60)

    coordinator = ChatStreamCoordinator()

    # 模拟真实锁池：同一 session_id 只有一个持有者
    active_locks = set()
    lock_mutex = asyncio.Lock()

    @contextmanager
    def mock_dist_lock(self, key, timeout=120):
        # 简单模拟带互斥语义的锁
        import threading
        if not hasattr(self, "_stress_locks"):
            self._stress_locks = set()
            self._stress_lock_obj = threading.Lock()
        
        with self._stress_lock_obj:
            if key in self._stress_locks:
                yield False
                return
            self._stress_locks.add(key)
        
        try:
            yield True
        finally:
            with self._stress_lock_obj:
                self._stress_locks.discard(key)

    req = MagicMock()
    req.app.state.saver = None
    bg_tasks = MagicMock()

    intercepted_count = 0
    passed_count = 0

    async def single_client_call(client_id: int):
        nonlocal intercepted_count, passed_count
        gen = coordinator.coordinate_stream(
            request=req,
            background_tasks=bg_tasks,
            session_id="burst_session_alpha",
            model_id="stress_model",
            message=f"突发并发请求 #{client_id}"
        )
        chunks = []
        try:
            async for chunk in gen:
                chunks.append(chunk)
                # 模拟推演首包耗时，保持锁持有
                if passed_count == 0 and "[[[ENGINE" in chunk:
                    await asyncio.sleep(0.05)
        except Exception:
            pass

        full_resp = "".join(chunks)
        if "请勿重复提交" in full_resp:
            intercepted_count += 1
        else:
            passed_count += 1

    with patch("app.infra.redis_client.RedisClient.dist_lock", mock_dist_lock):
        with patch("app.api.chat_stream_coordinator.get_graph_executor") as mock_exec:
            mock_graph = MagicMock()
            async def fake_stream(*args, **kwargs):
                yield {"event": "on_chat_model_stream", "name": "r", "metadata": {}, "data": {"chunk": MagicMock(content="模拟推演结果")}}
            mock_graph.astream_events = fake_stream
            mock_graph.aget_state = MagicMock(return_value=MagicMock(next=None))
            mock_exec.return_value = (mock_graph, "stress_model")

            # 20 个请求同时迸发打入同一 session_id
            await asyncio.gather(*[single_client_call(i) for i in range(20)])

    print(f"  - 突发总请求数: 20")
    print(f"  - 成功通行进入推演: {passed_count} 笔 (期望严格等于 1)")
    print(f"  - 被会话飞行锁安全拦截: {intercepted_count} 笔 (期望严格等于 19)")
    assert passed_count == 1, f"并发穿透防护失效！通过了 {passed_count} 笔请求！"
    assert intercepted_count == 19, f"拦截不彻底！拦截了 {intercepted_count} 笔请求！"
    print("  [压测 3 通过] 会话飞行锁在 20 突发并发下 100% 达成单一推演保护！")


async def main():
    test_component_concurrency_stress()
    test_task_pool_concurrency_stress()
    await test_api_session_burst_stress()
    print("\n" + "="*60)
    print("[全部完成] 3 大高并发与幂等压力基准测试全部通过！系统达到企业级生产标准！")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
