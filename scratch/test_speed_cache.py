import time
import sys
import os
sys.path.append(os.getcwd())

from app.infra.redis_client import redis_manager
from app.memory.semantic_memory import sql_cache_manager
from loguru import logger

def run_minimal_speed_test():
    logger.info("🚀 开始【审计缓存命中】最小化性能测试")
    
    # 1. 准备数据
    question = "核查2024年所有分解住院的线索"
    sql = "SELECT psn_no FROM header_table WHERE interval < 15"
    
    # 2. 预热：模拟第一次执行（存入 Redis）
    logger.info("--- 步骤 1: 模拟首次执行（存入分布式缓存） ---")
    sql_cache_manager.save(question, sql)
    
    # 3. 核心测试：模拟第二次重复提问，测量耗时
    logger.info("--- 步骤 2: 模拟重复提问（测量缓存命中耗时） ---")
    
    start_time = time.time()
    # 执行检索
    cached_sql = sql_cache_manager.search(question)
    end_time = time.time()
    
    duration_ms = (end_time - start_time) * 1000
    
    if cached_sql == sql:
        logger.success(f"🎯 缓存命中成功！")
        logger.success(f"⏱️ 检索耗时: {duration_ms:.2f} ms")
        if duration_ms < 300:
            logger.success("✅ 性能达标：响应时间远低于 300ms 阈值！")
    else:
        logger.error("❌ 缓存未命中，请检查 Redis 连接或 Embedding 配置")

if __name__ == "__main__":
    # 强制尝试连接
    if not redis_manager.is_connected:
        logger.warning("尝试通过无密码模式连接进行测试...")
        import redis
        try:
            redis_manager.client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            redis_manager.client.ping()
            redis_manager.is_connected = True
        except:
            pass
            
    run_minimal_speed_test()
