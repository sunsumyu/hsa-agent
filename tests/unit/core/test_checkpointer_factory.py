"""
Unit tests for the configurable checkpointer factory and production pitfall protections:
- Pitfall 1: Connection pool reuse vs single connection exhaustion
- Pitfall 2: autocommit=True and prepare_threshold=0 configuration
- Pitfall 3: State data structure purity and serialization safety
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 确保直接运行脚本时能正确定位到项目根目录 app
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import socket
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.core.checkpointer import (
    CheckpointerBackend,
    get_configured_backend,
    create_checkpointer,
    assert_state_serializable,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel


def test_default_backend_resolution():
    print("\n--- [测试 1: 默认后端解析] ---")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CHECKPOINTER_BACKEND", None)
        os.environ.pop("LANGGRAPH_CHECKPOINTER", None)
        backend = get_configured_backend()
        print(f"  -> 未设置任何环境变量时，默认解析为: {backend.value} (预期: sqlite)")
        assert backend == CheckpointerBackend.SQLITE
        print("  ✅ [通过] 默认后端正确回退至 SQLite")


def test_env_var_backend_resolution():
    print("\n--- [测试 2: 环境变量覆盖解析] ---")
    with patch.dict(os.environ, {"CHECKPOINTER_BACKEND": "postgres"}, clear=False):
        backend = get_configured_backend()
        print(f"  -> 设置 CHECKPOINTER_BACKEND='postgres'，解析为: {backend.value}")
        assert backend == CheckpointerBackend.POSTGRES

    with patch.dict(os.environ, {"CHECKPOINTER_BACKEND": "", "LANGGRAPH_CHECKPOINTER": "memory"}, clear=False):
        backend = get_configured_backend()
        print(f"  -> 设置 LANGGRAPH_CHECKPOINTER='memory'，解析为: {backend.value}")
        assert backend == CheckpointerBackend.MEMORY
    print("  ✅ [通过] 环境变量正确驱动多后端切换")


@pytest.mark.asyncio
async def test_create_memory_checkpointer():
    print("\n--- [测试 3: MemorySaver 临时内存后端创建] ---")
    async with create_checkpointer(backend=CheckpointerBackend.MEMORY) as saver:
        print(f"  -> 创建的 Checkpointer 实例类型: {saver.__class__.__name__}")
        assert isinstance(saver, MemorySaver)
        print("  ✅ [通过] MemorySaver 无盘测试后端就绪")


@pytest.mark.asyncio
async def test_create_sqlite_checkpointer(tmp_path):
    print("\n--- [测试 4: SQLite 嵌入式后端与兼容性补丁创建] ---")
    db_file = str(tmp_path / "test_checkpoints.db")
    async with create_checkpointer(backend=CheckpointerBackend.SQLITE, conn_string=db_file) as saver:
        print(f"  -> SQLite 本地数据库文件: {db_file}")
        print(f"  -> Saver 实例类型: {saver.__class__.__name__}")
        assert isinstance(saver, AsyncSqliteSaver)
        
        target = getattr(saver, "conn", None) or getattr(saver, "connection", None)
        if target:
            is_alive_fn = getattr(target, "is_alive", None)
            is_alive_val = is_alive_fn() if callable(is_alive_fn) else None
            print(f"  -> 注入的 aiosqlite 连接 is_alive 兼容性补丁存在且返回: {is_alive_val}")
            assert callable(is_alive_fn)
            assert is_alive_val is True
        print("  ✅ [通过] AsyncSqliteSaver 创建及 aiosqlite 补丁生效")


# =============================================================================
# 坑点 1 & 坑点 2 专项测试：连接池注入、autocommit 事务与单次 setup 初始化
# =============================================================================
@pytest.mark.asyncio
async def test_postgres_pitfall_1_and_2_pool_autocommit():
    """
    验证：
    1. 使用 AsyncConnectionPool 而非单连接 (规避连接打满)。
    2. 显式传递 autocommit=True, prepare_threshold=0 (规避隐式事务锁等待)。
    3. setup() 仅在启动时执行一次。
    """
    print("\n--- [测试 5: Postgres 生产级避坑验证 (坑点 1 & 2)] ---")
    from psycopg_pool import AsyncConnectionPool

    captured_init_kwargs = {}
    orig_init = AsyncConnectionPool.__init__

    def mock_init(self, conninfo, **kwargs):
        captured_init_kwargs["conninfo"] = conninfo
        captured_init_kwargs.update(kwargs)
        self._conninfo = conninfo

    with patch.object(AsyncConnectionPool, "__init__", side_effect=mock_init, autospec=True):
        with patch.object(AsyncConnectionPool, "__aenter__", new_callable=AsyncMock) as mock_aenter:
            with patch.object(AsyncConnectionPool, "__aexit__", new_callable=AsyncMock):
                with patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.setup", new_callable=AsyncMock) as mock_setup:
                    mock_pool = MagicMock(spec=AsyncConnectionPool)
                    mock_aenter.return_value = mock_pool

                    target_uri = "postgresql://audit_admin:pass@db:5432/hsa"
                    async with create_checkpointer(
                        backend=CheckpointerBackend.POSTGRES,
                        conn_string=target_uri,
                        pool_max_size=30,
                    ) as saver:
                        print(f"  -> 连接信息 (conninfo): {captured_init_kwargs['conninfo']}")
                        print(f"  -> 连接池容量 (max_size): {captured_init_kwargs['max_size']} (成功使用 AsyncConnectionPool 避免单连接耗尽)")
                        assert captured_init_kwargs["conninfo"] == target_uri
                        assert captured_init_kwargs["max_size"] == 30
                        
                        conn_kwargs = captured_init_kwargs["kwargs"]
                        print(f"  -> 连接池事务参数: autocommit={conn_kwargs['autocommit']}, prepare_threshold={conn_kwargs['prepare_threshold']}")
                        assert conn_kwargs["autocommit"] is True
                        assert conn_kwargs["prepare_threshold"] == 0
                        print("     ↳ [规避坑点 2] 显式开启 autocommit=True，防止长事务锁等待与回滚")
                        print("     ↳ [优化] prepare_threshold=0 适配 PgBouncer 事务连接池")

                        mock_setup.assert_awaited_once()
                        print(f"  -> DDL 建表 setup() 调用次数: {mock_setup.await_count} 次 (规避坑点 1: 全局应用启动仅做一次初始化)")

                        assert saver.conn == mock_pool
                        print(f"  -> AsyncPostgresSaver 底层连接绑定: {saver.conn.__class__.__name__} 连接池对象")
        print("  ✅ [通过] Postgres 连接池化 + autocommit 事务参数验证完毕")


# =============================================================================
# 坑点 3 专项测试：State 序列化安全性校验 (JsonPlusSerializer)
# =============================================================================
class SampleAuditState(BaseModel):
    session_id: str
    risk_score: float
    items: list[str]


def test_state_serialization_success_cases():
    print("\n--- [测试 6: State 序列化纯数据白名单校验 (坑点 3 正向测试)] ---")
    # 纯字典与基础类型
    dict_payload = {"step": 1, "query": "SELECT 1", "metrics": [10.5, 20.0]}
    valid, err = assert_state_serializable(dict_payload)
    print(f"  -> 基础数据结构序列化测试: valid={valid}")
    assert valid is True
    assert err is None

    # Pydantic 模型
    pydantic_payload = SampleAuditState(session_id="S100", risk_score=95.5, items=["itemA"])
    valid, err = assert_state_serializable(pydantic_payload)
    print(f"  -> Pydantic 审计状态对象序列化测试: valid={valid}")
    assert valid is True
    assert err is None

    # LangChain 标准消息
    lc_payload = {
        "messages": [
            HumanMessage(content="查询医保违规流水"),
            AIMessage(content="正在分析中...")
        ]
    }
    valid, err = assert_state_serializable(lc_payload)
    print(f"  -> LangChain BaseMessage 消息列表序列化测试: valid={valid}")
    assert valid is True
    assert err is None
    print("  ✅ [通过] 纯数据结构、Pydantic DTO 与 BaseMessage 100% 序列化安全")


def test_state_serialization_failure_pitfall_3():
    print("\n--- [测试 7: State 混入非法不可序列化对象拦截测试 (规避坑点 3)] ---")
    s = socket.socket()
    try:
        invalid_state = {
            "session_id": "S101",
            "active_socket": s,  # 非法对象：套接字
        }
        print(f"  -> 构造包含非法对象的 State: active_socket={s}")
        valid, err = assert_state_serializable(invalid_state)
        print(f"  -> 序列化校验探测结果: valid={valid}")
        print(f"  -> 捕获到的拦截诊断详情: {err}")
        assert valid is False
        assert "TypeError" in err or "serializable" in err.lower()
        print("  ✅ [通过] 非序列化对象被 assert_state_serializable 守卫成功捕获并定位，防止运行时硬崩溃！")
    finally:
        s.close()


if __name__ == "__main__":
    import asyncio
    print("\n" + "=" * 70)
    print("🚀 直接以 Python 脚本方式执行 Checkpointer 工厂全套测试")
    print("=" * 70)
    test_default_backend_resolution()
    test_env_var_backend_resolution()
    asyncio.run(test_create_memory_checkpointer())
    # 模拟 tmp_path
    import pathlib, tempfile
    with tempfile.TemporaryDirectory() as td:
        asyncio.run(test_create_sqlite_checkpointer(pathlib.Path(td)))
    asyncio.run(test_postgres_pitfall_1_and_2_pool_autocommit())
    test_state_serialization_success_cases()
    test_state_serialization_failure_pitfall_3()
    print("\n" + "=" * 70)
    print("🎉 恭喜！全部 7 项测试与 3 大避坑指南验证 100% 通过！")
    print("=" * 70 + "\n")
