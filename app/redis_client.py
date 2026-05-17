import os
import json
import time
from typing import Optional, Any
from loguru import logger

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

class RedisClient:
    """[V140.0] 企业级 Redis 客户端：支持自动降级与语义缓存管理。"""
    
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
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                socket_timeout=2,
                decode_responses=True
            )
            # 测试连接
            self.client.ping()
            self.is_connected = True
            logger.success(f"🚀 [REDIS] 成功连接至 {self.host}:{self.port}")
        except Exception as e:
            logger.warning(f"⚠️ [REDIS] 连接失败 (可能是未启动服务): {e}。已切换至本地 Mock 模式。")
            self.is_connected = False

    def set_cache(self, key: str, value: Any, expire_hours: int = 24):
        """写入缓存，支持字典自动序列化。"""
        if not self.is_connected: return
        try:
            val_str = json.dumps(value, ensure_ascii=False)
            self.client.setex(f"hsa:cache:{key}", expire_hours * 3600, val_str)
        except Exception as e:
            logger.error(f"❌ [REDIS_SET] 写入异常: {e}")

    def get_cache(self, key: str) -> Optional[Any]:
        """读取缓存，自动反序列化。"""
        if not self.is_connected: return None
        try:
            data = self.client.get(f"hsa:cache:{key}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"❌ [REDIS_GET] 读取异常: {e}")
            return None

    def record_node_health(self, node_id: str, is_healthy: bool):
        """[V140.1] 使用 Redis 存储分布式节点健康状态。"""
        if not self.is_connected: return
        try:
            status = "UP" if is_healthy else "DOWN"
            self.client.hset("hsa:nodes:health", node_id, json.dumps({
                "status": status,
                "last_update": time.time()
            }))
        except Exception as e:
            logger.error(f"❌ [REDIS_HEALTH] 写入异常: {e}")

    from contextlib import contextmanager
    @contextmanager
    def dist_lock(self, lock_key: str, timeout: int = 10):
        """[V4.5] 企业级分布式锁实现"""
        if not self.is_connected:
            yield None
            return
            
        acquired = False
        try:
            # 尝试获取锁 (NX=True 表示不存在才设置, EX=timeout 设置过期防止死锁)
            acquired = self.client.set(f"hsa:lock:{lock_key}", "LOCKED", nx=True, ex=timeout)
            if acquired:
                logger.debug(f"🔓 [REDIS] 成功获取分布式锁: {lock_key}")
                yield True
            else:
                logger.warning(f"🔒 [REDIS] 获取锁失败 (冲突): {lock_key}")
                yield False
        finally:
            if acquired:
                self.client.delete(f"hsa:lock:{lock_key}")
                logger.debug(f"🔐 [REDIS] 已释放分布式锁: {lock_key}")

redis_manager = RedisClient()
