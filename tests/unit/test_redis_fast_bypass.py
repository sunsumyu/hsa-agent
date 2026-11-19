import os
import time
import pytest
from app.infra.redis_client import RedisClient

def test_redis_fast_bypass_when_cache_disabled(monkeypatch):
    """验证评测/离线模式下，RedisClient 0ms 瞬间旁路，杜绝阻塞主流水线"""
    monkeypatch.setenv("DISABLE_AUDIT_CACHE", "true")
    
    start = time.perf_counter()
    client = RedisClient()
    elapsed = time.perf_counter() - start
    
    assert client.is_connected is False
    assert elapsed < 0.05, f"Redis 旁路耗时过长: {elapsed:.3f}s"

def test_redis_connect_timeout_short(monkeypatch):
    """验证即使未禁用缓存，在 Redis 服务未启动时，连接超时也能在 500ms 内快速降级，杜绝 Windows 20s+ 假死"""
    monkeypatch.delenv("DISABLE_AUDIT_CACHE", raising=False)
    monkeypatch.delenv("REDIS_DISABLED", raising=False)
    # 模拟指向一个不可达的本地端口
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "63799")
    
    start = time.perf_counter()
    client = RedisClient()
    elapsed = time.perf_counter() - start
    
    assert client.is_connected is False
    assert elapsed < 1.0, f"Redis 失败降级超时过长: {elapsed:.3f}s"
