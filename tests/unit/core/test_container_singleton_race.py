"""
tests/unit/core/test_container_singleton_race.py
================================================
[P0-2] ServiceProvider.resolve 单例互斥反向验证。

旧实现: check-construct-assign 无锁。LazyProxy 每次属性访问都走 resolve,
工作线程并发首次解析时各自执行工厂 → 双实例:
各持独立 _lock 与独立 stats (状态永久分裂、互相覆盖), 持连接资源双份泄漏。
判定标准: 旧实现必然红灯 (工厂被调用多次 / 实例不唯一)。
"""

import threading
import time

import pytest

from app.core.container import ServiceProvider


@pytest.fixture(autouse=True)
def clean_container():
    ServiceProvider.reset()
    yield
    ServiceProvider.reset()


def test_concurrent_first_resolve_creates_exactly_one_instance():
    calls = []

    def slow_factory():
        calls.append(1)
        time.sleep(0.05)  # 拉长 check-construct-assign 窗口
        return object()

    ServiceProvider.register("race_svc", slow_factory)

    N = 8
    barrier = threading.Barrier(N)
    results = [None] * N

    def worker(i):
        barrier.wait(timeout=5)
        results[i] = ServiceProvider.resolve("race_svc")

    threads = [
        threading.Thread(target=worker, name=f"resolve-{i}", args=(i,))
        for i in range(N)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert all(not t.is_alive() for t in threads), "resolve 并发路径死锁"

    assert len(calls) == 1, (
        f"并发首次解析工厂被调用 {len(calls)} 次 (旧实现 check-construct-assign 无锁)"
    )
    assert len({id(r) for r in results}) == 1, (
        "并发首次解析产出多个实例 (状态分裂 / 资源双份泄漏)"
    )


def test_factory_dependency_resolution_survives_reentrant_resolve():
    """工厂在锁内回调 resolve 解析依赖 — 互斥必须可重入 (RLock), 否则自死锁。"""
    ServiceProvider.register("dep", lambda: "DEP")

    def outer_factory():
        return ServiceProvider.resolve("dep") + "-OK"

    ServiceProvider.register("outer", outer_factory)
    assert ServiceProvider.resolve("outer") == "DEP-OK"
