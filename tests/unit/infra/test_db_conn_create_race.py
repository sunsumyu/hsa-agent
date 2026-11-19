"""
tests/unit/infra/test_db_conn_create_race.py
============================================
[P1-5] get_clickhouse_client 全局客户端并发建连反向验证。

旧实现: 建连无锁。该函数被 asyncio.to_thread 的 SQL 路径并发调用,
并发首次调用各自执行完整探测链 (socket 预检 + wsl 子进程 + 多次 SELECT 1),
各自建 CharsetProxy 后互相覆盖 → 连接泄漏; 健康检查失败置 None 还会诱发重建风暴。
判定标准: 旧实现必然红灯 (驱动工厂被调用多次 / 实例不唯一)。
"""

import threading
import time

import pytest

from app.infra import db_conn


class FakeHTTPClient:
    def query(self, sql):
        assert sql == "SELECT 1"
        return None


@pytest.fixture
def clean_global_client():
    db_conn._CK_GLOBAL_CLIENT = None
    yield
    db_conn._CK_GLOBAL_CLIENT = None


def test_concurrent_first_connect_builds_single_client(clean_global_client, monkeypatch):
    import socket
    import subprocess

    # 路径 1: 让 9000 端口预检失败 (不触网)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, addr: 1)

    # 路径 2: 让 WSL IP 探测返回空列表 (不执行真实子进程)
    class _FakeProc:
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeProc())

    # 路径 3: 拦截真实驱动工厂, 统计调用次数并拉长建连窗口
    created = []

    def fake_get_client(**kwargs):
        created.append(1)
        time.sleep(0.25)  # 拉长 check-construct-assign 窗口
        return FakeHTTPClient()

    monkeypatch.setattr(db_conn.clickhouse_connect, "get_client", fake_get_client)

    N = 8
    barrier = threading.Barrier(N)
    results = [None] * N

    def worker(i):
        barrier.wait(timeout=5)
        results[i] = db_conn.get_clickhouse_client()

    threads = [
        threading.Thread(target=worker, name=f"ck-connect-{i}", args=(i,))
        for i in range(N)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert all(not t.is_alive() for t in threads), "get_clickhouse_client 并发路径死锁"

    assert len(created) == 1, (
        f"并发首次建连驱动工厂被调用 {len(created)} 次 (旧实现无锁 → 重复探测链 + 连接泄漏)"
    )
    assert len({id(r) for r in results}) == 1, (
        "并发建连产出多个全局客户端实例 (互相覆盖 / 泄漏)"
    )
