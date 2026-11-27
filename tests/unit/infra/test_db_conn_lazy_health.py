"""
tests/unit/infra/test_db_conn_lazy_health.py
============================================
[方案4] get_clickhouse_client 懒校验 + 传输层自愈反向验证。

判定标准: 旧实现必然红灯。
- 旧实现每次 get_clickhouse_client 都执行 SELECT 1 探活 →
  每条 SQL 隐形双倍 RTT (必红);
- 旧实现无自愈重试 → 连接失效后首个调用方直接吃 SqlExecError (必红);
- 旧实现无建连失败冷却 → 服务下线期间每次调用都跑完整探测链 (重建风暴, 必红)。
新实现: 快路径直返 + 查询失败单飞重建 + 重试一次 + 失败冷却窗口。
"""

import socket
import subprocess

import pytest

from app.infra import db_conn
from app.infra.db_conn import CharsetProxy, SqlExecError


@pytest.fixture
def clean_ck_globals():
    db_conn._CK_GLOBAL_CLIENT = None
    if hasattr(db_conn, "_CK_LAST_BUILD_FAIL_TS"):
        db_conn._CK_LAST_BUILD_FAIL_TS = 0.0
    yield
    db_conn._CK_GLOBAL_CLIENT = None
    if hasattr(db_conn, "_CK_LAST_BUILD_FAIL_TS"):
        db_conn._CK_LAST_BUILD_FAIL_TS = 0.0


def _patch_offline_paths(monkeypatch):
    """让路径 1/2 (socket 预检 / WSL 探测) 静默失败, 只走路径 3。"""
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, addr: 1)

    class _FakeProc:
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeProc())


def test_fast_path_does_not_probe_on_every_call(clean_ck_globals, monkeypatch):
    """反向验证: 快路径不得每次调用都执行 SELECT 1 探活 (每条 SQL 隐形双倍 RTT)。

    旧实现: 第二次 get_clickhouse_client 会再跑一次 SELECT 1 → 计数增长 (必红)。
    新实现: 建连期验证一次, 之后直返全局单例, 计数不变 (绿)。
    """
    _patch_offline_paths(monkeypatch)
    health_calls = []

    class CountingClient:
        def query(self, sql):
            health_calls.append(sql)
            return None

    monkeypatch.setattr(
        db_conn.clickhouse_connect, "get_client", lambda **kw: CountingClient()
    )

    first = db_conn.get_clickhouse_client()
    calls_after_build = len(health_calls)
    assert calls_after_build >= 1, "建连期必须完成一次验证 (SELECT 1)"

    second = db_conn.get_clickhouse_client()
    assert second is first, "全局单例必须复用"
    assert len(health_calls) == calls_after_build, (
        f"快路径执行了探活查询 (SELECT 1 调用数 {calls_after_build} → {len(health_calls)}): "
        "每条 SQL 隐形双倍 RTT"
    )


def test_transport_failure_self_heals_via_rebuild_and_retry_once(clean_ck_globals, monkeypatch):
    """反向验证: 传输层故障必须重建连接并重试一次, 调用方无感。

    旧实现: 无自愈 → 首个调用方直接吃 SqlExecError, 且全局客户端永久僵死 (必红)。
    新实现: 单飞重建 → 新客户端上重试成功 (绿)。
    """
    driver_calls = []

    class FlakyClient:
        def query(self, sql):
            driver_calls.append(sql)
            if len(driver_calls) == 1:
                raise RuntimeError(
                    "Error HTTPConnectionPool(host='localhost', port=8223): "
                    "Max retries exceeded ... executing HTTP request attempt 1 "
                    "(Caused by NewConnectionError: [WinError 10061] 由于目标计算机积极拒绝，无法连接。)"
                )
            return None

    broken = CharsetProxy(FlakyClient())
    fresh_holder = []

    class CountingFreshClient:
        def __init__(self):
            self.calls = []

        def query(self, sql):
            self.calls.append(sql)
            return None

    fresh_client = CountingFreshClient()

    def fake_rebuild(stale_proxy):
        fresh_holder.append(1)
        return CharsetProxy(fresh_client)

    monkeypatch.setattr(db_conn, "_rebuild_after_failure", fake_rebuild, raising=False)

    result = broken.query("SELECT 1")
    assert result == [], "重试必须返回新客户端的正常结果"
    assert len(fresh_holder) == 1, "重建必须单飞 (恰好一次)"
    assert len(driver_calls) == 1 and len(fresh_client.calls) == 1, (
        f"传输层故障应恰好触发一次重建 + 一次重试 "
        f"(坏客户端 {len(driver_calls)} 次 / 新客户端 {len(fresh_client.calls)} 次)"
    )


def test_server_side_errors_do_not_trigger_rebuild(monkeypatch):
    """回归护栏: 服务端拒绝 (语法错误等) 不得触发重建。

    否则每条坏 SQL 都白付一次探测链 (WSL 子进程探活最贵 3s)。
    旧实现本就无重建, 此为防新实现误伤的护栏 (新旧实现均应绿)。
    """
    rebuild_calls = []
    monkeypatch.setattr(
        db_conn, "_rebuild_after_failure", lambda stale: rebuild_calls.append(1),
        raising=False,
    )

    class ServerErrorClient:
        def query(self, sql):
            raise RuntimeError(
                "Received ClickHouse exception, code: 62, "
                "server response: Syntax error (Multi-statements are not allowed)"
            )

    proxy = CharsetProxy(ServerErrorClient())

    with pytest.raises(SqlExecError):
        proxy.query("SELECT bad")
    assert rebuild_calls == [], "服务端错误不得触发重建"


def test_build_cooldown_prevents_rebuild_storm(clean_ck_globals, monkeypatch):
    """反向验证: 建连失败后的冷却窗口内, 不得再执行完整探测链 (重建风暴)。

    旧实现: 每次调用都跑完整探测链 (socket 预检 + wsl 子进程 + HTTP) → 工厂被
    反复调用 (必红)。
    新实现: 失败后 5s 冷却, 第二次调用快速失败, 驱动工厂不再被调用 (绿)。
    """
    _patch_offline_paths(monkeypatch)
    factory_calls = []

    def failing_get_client(**kw):
        factory_calls.append(1)
        raise RuntimeError(
            "Error HTTPConnectionPool(host='localhost', port=8223): "
            "Failed to establish a new connection: [WinError 10061] 拒绝连接"
        )

    monkeypatch.setattr(db_conn.clickhouse_connect, "get_client", failing_get_client)

    with pytest.raises(RuntimeError):
        db_conn.get_clickhouse_client()
    with pytest.raises(RuntimeError):
        db_conn.get_clickhouse_client()

    assert len(factory_calls) == 1, (
        f"冷却窗口内驱动工厂被调用 {len(factory_calls)} 次: "
        "服务下线期间每个调用方都串行执行完整探测链 (重建风暴)"
    )
