import pytest
from unittest.mock import MagicMock
from app.infra.redis_client import RedisClient

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.eval_calls = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        return self.store.pop(key, None) is not None

    def eval(self, script, numkeys, key, arg):
        self.eval_calls.append((script, key, arg))
        # Lua semantics: if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) else return 0 end
        if self.store.get(key) == str(arg):
            del self.store[key]
            return 1
        return 0


def test_dist_lock_uses_unique_token_and_lua_release():
    """RED 测试：分布式锁必须使用随机 Token (非静态 LOCKED) 并在退出时通过 Lua 脚本原子释放"""
    client = RedisClient.__new__(RedisClient)
    client.is_connected = True
    fake_redis = FakeRedis()
    client.client = fake_redis

    lock_key = "tenant_1001"
    full_key = f"argus:lock:{lock_key}"

    with client.dist_lock(lock_key, timeout=15) as acquired:
        assert acquired is True
        stored_val = fake_redis.store.get(full_key)
        assert stored_val is not None
        # 必须是随机 Token (例如 UUID)，严禁使用静态 'LOCKED'
        assert stored_val != "LOCKED"
        assert len(stored_val) >= 16

    # 退出上下文后，必须通过 eval 执行 Lua 脚本释放，且 key 已被删除
    assert full_key not in fake_redis.store
    assert len(fake_redis.eval_calls) == 1
    script, eval_key, eval_token = fake_redis.eval_calls[0]
    assert "redis.call" in script
    assert eval_key == full_key
    assert eval_token == stored_val


def test_dist_lock_does_not_delete_foreign_token_on_timeout():
    """RED 测试：若锁已超时并被其他线程/节点持有新 Token，当前退出时绝对不能误删他人的锁"""
    client = RedisClient.__new__(RedisClient)
    client.is_connected = True
    fake_redis = FakeRedis()
    client.client = fake_redis

    lock_key = "tenant_timeout"
    full_key = f"argus:lock:{lock_key}"

    with client.dist_lock(lock_key, timeout=5) as acquired:
        assert acquired is True
        # 模拟执行超时，另外一个 worker B 获取到了新锁
        fake_redis.store[full_key] = "foreign-worker-uuid-9999"

    # 原 worker 退出上下文，执行 release 时，发现 Token 不匹配，不能删除 worker B 的锁
    assert full_key in fake_redis.store
    assert fake_redis.store[full_key] == "foreign-worker-uuid-9999"
