import os
import json
import time
import uuid
from typing import Optional, Any
from contextlib import contextmanager
from loguru import logger

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

class RedisClient:
    """[V140.0] 企业级 Redis 客户端：支持自动降级与语义缓存管理。"""

    # 预加载释放锁的 Lua 脚本：只有持有者 Token 一致才允许删除
    RELEASE_LOCK_LUA = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.db = int(os.getenv("REDIS_DB", 0))
        self.password = os.getenv("REDIS_PASSWORD")
        self.client: Optional[Any] = None
        self.is_connected = False
        
        if _REDIS_AVAILABLE:
            self._connect()
        else:
            logger.warning("⚠️ [REDIS] 未安装 redis 库，系统将降级为本地内存缓存模式。")

    def _connect(self):
        # 评测或离线模式下 0ms 秒级直通旁路
        if os.getenv("DISABLE_AUDIT_CACHE", "").lower() in ("true", "1") or os.getenv("REDIS_DISABLED", "").lower() in ("true", "1"):
            logger.info("⚡ [REDIS] 检测到离线/评测模式，自动旁路跳过 Redis 连接。")
            self.is_connected = False
            return

        import socket
        try:
            # 原生轻量底层探测：若目标端口不可达，0.2 秒内直接熔断返回，绝不阻塞主流水线
            with socket.create_connection((self.host, self.port), timeout=0.2):
                pass
        except (OSError, socket.timeout) as sock_err:
            logger.warning(f"⚠️ [REDIS] 快速探活失败 ({self.host}:{self.port} 不可达: {sock_err})。秒级切换至旁路降级模式。")
            self.is_connected = False
            return

        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                socket_timeout=0.5,
                socket_connect_timeout=0.2,
                decode_responses=True
            )
            # 测试连接
            self.client.ping()
            self.is_connected = True
            logger.success(f"🚀 [REDIS] 成功连接至 {self.host}:{self.port}")
        except Exception as e:
            logger.warning(f"⚠️ [REDIS] 连接失败 (可能是未启动服务): {e}。已切换至旁路降级模式（无缓存直通运行）。")
            self.is_connected = False

    def set_cache(self, key: str, value: Any, expire_hours: int = 24):
        """写入缓存，支持字典自动序列化。"""
        if not self.is_connected: return
        try:
            val_str = json.dumps(value, ensure_ascii=False)
            self.client.setex(f"argus:cache:{key}", expire_hours * 3600, val_str)
        except Exception as e:
            logger.error(f"❌ [REDIS_SET] 写入异常: {e}")

    def get_cache(self, key: str) -> Optional[Any]:
        """读取缓存，自动反序列化。"""
        if not self.is_connected: return None
        try:
            data = self.client.get(f"argus:cache:{key}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"❌ [REDIS_GET] 读取异常: {e}")
            return None

    def record_node_health(self, node_id: str, is_healthy: bool):
        """[V140.1] 使用 Redis 存储分布式节点健康状态。"""
        if not self.is_connected: return
        try:
            status = "UP" if is_healthy else "DOWN"
            self.client.hset("argus:nodes:health", node_id, json.dumps({
                "status": status,
                "last_update": time.time()
            }))
        except Exception as e:
            logger.error(f"❌ [REDIS_HEALTH] 写入异常: {e}")

    @contextmanager
    def dist_lock(self, lock_key: str, timeout: int = 10):
        """[V4.6 企业加固] 分布式锁实现：使用 UUID Token 与 Lua 脚本原子释放，防止超时误删他人锁"""
        if not self.is_connected or self.client is None:
            yield None
            return

        lock_token = str(uuid.uuid4())
        full_key = f"argus:lock:{lock_key}"
        acquired = False
        try:
            # 尝试获取锁 (NX=True 表示不存在才设置, EX=timeout 设置过期防止死锁)
            acquired = bool(self.client.set(full_key, lock_token, nx=True, ex=timeout))
            if acquired:
                logger.debug(f"🔓 [REDIS] 成功获取分布式锁: {lock_key} (Token: {lock_token[:8]})")
                yield True
            else:
                logger.warning(f"🔒 [REDIS] 获取锁失败 (冲突): {lock_key}")
                yield False
        finally:
            if acquired:
                try:
                    if hasattr(self.client, "eval"):
                        self.client.eval(self.RELEASE_LOCK_LUA, 1, full_key, lock_token)
                    else:
                        self.client.delete(full_key)
                    logger.debug(f"🔐 [REDIS] 已释放分布式锁: {lock_key}")
                except Exception as e:
                    logger.error(f"❌ [REDIS] 释放分布式锁异常: {e}")

# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

redis_manager = LazyProxy("redis_manager")
