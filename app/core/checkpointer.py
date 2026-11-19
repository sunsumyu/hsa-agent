"""
app/core/checkpointer.py
========================
[V220.0] Configurable Checkpointer Factory & Abstraction Layer.

Supports runtime / environment-driven switching between:
  1. SQLITE (default, edge/local private deployment via audit_checkpoints.db)
  2. POSTGRES (enterprise cloud-native multi-pod cluster via AsyncPostgresSaver + AsyncConnectionPool)
  3. MEMORY (stateless / ephemeral testing via MemorySaver)

Production Pitfall Protections:
  - Pitfall 1: Uses AsyncConnectionPool instead of single connections, initialized once at lifespan.
  - Pitfall 2: Enforces autocommit=True, prepare_threshold=0, and dict_row to prevent lock waits.
  - Pitfall 3: Provides assert_state_serializable() guard to prevent unpicklable objects in State.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional, Union, AsyncIterator, Any, Tuple
from contextlib import asynccontextmanager
from loguru import logger


class CheckpointerBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MEMORY = "memory"


def get_configured_backend() -> CheckpointerBackend:
    """Read the configured checkpointer backend from environment variables."""
    raw = os.getenv("CHECKPOINTER_BACKEND") or os.getenv("LANGGRAPH_CHECKPOINTER")
    if not raw:
        return CheckpointerBackend.SQLITE
    cleaned = raw.strip().lower()
    try:
        return CheckpointerBackend(cleaned)
    except ValueError:
        logger.warning(f"[Checkpointer] 未知后端配置 '{raw}'，自动回退至默认 SQLite 后端")
        return CheckpointerBackend.SQLITE


def assert_state_serializable(state: Any) -> Tuple[bool, Optional[str]]:
    """
    [避坑点 3 预检守卫] 验证 State 数据结构的纯度与可序列化性。
    
    检测 State 中是否混入了未序列化的套接字、连接池句柄或复杂自定义实例，
    避免在 Superstep 提交写入 checkpoint_blobs 时触发硬崩溃。
    """
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serializer = JsonPlusSerializer()
    try:
        serializer.dumps_typed(state)
        return True, None
    except Exception as exc:
        err_msg = f"State 包含不可序列化对象: {type(exc).__name__} - {str(exc)}"
        logger.error(f"[StateGuard] 序列化校验失败: {err_msg}")
        return False, err_msg


@asynccontextmanager
async def create_checkpointer(
    backend: Optional[Union[str, CheckpointerBackend]] = None,
    conn_string: Optional[str] = None,
    pool_max_size: Optional[int] = None,
) -> AsyncIterator[Any]:
    """
    Asynchronous context manager factory yielding a configured LangGraph checkpointer.

    Usage (FastAPI lifespan):
        async with create_checkpointer() as saver:
            app.state.saver = saver
    """
    if backend is None:
        target_backend = get_configured_backend()
    elif isinstance(backend, str):
        target_backend = CheckpointerBackend(backend.strip().lower())
    else:
        target_backend = backend

    logger.info(f">>> [持久化工厂] 正在初始化 Checkpointer 后端: {target_backend.value.upper()}")

    if target_backend == CheckpointerBackend.MEMORY:
        from langgraph.checkpoint.memory import MemorySaver
        saver = MemorySaver()
        logger.info(">>> [持久化工厂] MemorySaver (内存临时存储) 就绪")
        yield saver

    elif target_backend == CheckpointerBackend.POSTGRES:
        # [避坑点 1 & 2] 使用全局 AsyncConnectionPool 替代单连接 from_conn_string
        from psycopg_pool import AsyncConnectionPool
        from psycopg.rows import dict_row
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        effective_conn = (
            conn_string
            or os.getenv("POSTGRES_URI")
            or os.getenv("CHECKPOINTER_POSTGRES_URI")
            or "postgresql://audit_admin:audit_secret@localhost:5432/hsa_main"
        )
        max_size = pool_max_size or int(os.getenv("POSTGRES_POOL_MAX_SIZE", "20"))
        
        # 显式配置 autocommit=True, prepare_threshold=0 以及 dict_row
        connection_kwargs = {
            "autocommit": True,          # 规避坑点 2：避免隐式事务锁等待与未提交失效
            "prepare_threshold": 0,      # 适配 PgBouncer/池化模式，避免预编译重名冲突
            "row_factory": dict_row,     # LangGraph postgres saver 要求的 dict 字典映射
        }

        logger.debug(f">>> [持久化工厂] 正在创建 Postgres 异步连接池 (max_size={max_size})...")
        async with AsyncConnectionPool(
            conninfo=effective_conn,
            max_size=max_size,
            kwargs=connection_kwargs,
        ) as pool:
            # 将连接池传入 AsyncPostgresSaver
            saver = AsyncPostgresSaver(conn=pool)
            
            # [避坑点 1] 仅在应用启动 lifespan 阶段执行一次表结构检查与创建
            try:
                await saver.setup()
                logger.info(">>> [持久化工厂] PostgresSaver 检查点表结构已确认 (setup 完成)")
            except Exception as e:
                logger.warning(f">>> [持久化工厂] PostgresSaver setup 阶段提示: {e}")

            logger.info(">>> [持久化工厂] AsyncPostgresSaver (基于 AsyncConnectionPool) 生产就绪")
            yield saver

    else:
        # 默认：SQLITE
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        effective_db = (
            conn_string
            or os.getenv("SQLITE_CHECKPOINT_PATH")
            or "audit_checkpoints.db"
        )
        async with AsyncSqliteSaver.from_conn_string(effective_db) as saver:
            # 兼容性补丁：处理可能的属性缺失 (针对 aio-sqlite 连接对象)
            target = getattr(saver, "conn", None) or getattr(saver, "connection", None)
            if target and not hasattr(target, "is_alive"):
                logger.debug(">>> [持久化工厂] 注入 aio-sqlite 异步连接 is_alive 兼容性补丁")
                target.is_alive = lambda: True

            logger.info(f">>> [持久化工厂] AsyncSqliteSaver (本地嵌入式存储: {effective_db}) 就绪")
            yield saver
