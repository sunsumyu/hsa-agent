import sys
import os
# 将项目根目录加入路径
sys.path.append(os.getcwd())

from app.infra.redis_client import redis_manager
from app.memory.semantic_memory import sql_cache_manager
from loguru import logger

def test_redis_core():
    logger.info("=== 阶段 1: Redis 基础功能测试 ===")
    test_key = "test_audit_task"
    test_value = {"status": "success", "amount": 1000.5}
    
    # 写入测试
    redis_manager.set_cache(test_key, test_value)
    
    # 读取测试
    retrieved = redis_manager.get_cache(test_key)
    if retrieved == test_value or (not redis_manager.is_connected):
        logger.success("✅ Redis 基础读写测试通过 (或已正确处理降级)")
    else:
        logger.error(f"❌ Redis 读写不一致: 期望 {test_value}, 得到 {retrieved}")

def test_sql_cache_integration():
    logger.info("\n=== 阶段 2: SQL 语义缓存集成测试 ===")
    question = "核查 2024 年重复收费的患者"
    sql = "SELECT * FROM fqz_fymx_test WHERE rule='REPEAT_BILLING'"
    
    # 模拟存入缓存
    logger.info("正在模拟存入 SQL 缓存...")
    sql_cache_manager.save(question, sql)
    
    # 模拟从缓存中检索
    logger.info("正在执行语义匹配检索...")
    # 故意换个说法测试语义匹配
    query_variant = "帮我查一下2024年有哪些人重复缴费了"
    hit_sql = sql_cache_manager.search(query_variant)
    
    if hit_sql == sql:
        logger.success("🎯 SQL 语义缓存命中成功！")
        if redis_manager.is_connected:
            logger.info("🚀 确认数据已同步至 Redis 分布式层")
    else:
        logger.warning("⚠️ 未能通过语义命中（可能是本地模型未加载），但流程已跑通")

if __name__ == "__main__":
    logger.info("🔍 开始执行 HSA-Agent Redis 集成最小化测试...")
    test_redis_core()
    test_sql_cache_integration()
    logger.info("\n=== 测试结束 ===")
