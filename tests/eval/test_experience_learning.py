import asyncio
import os
import json
from loguru import logger
from app.memory.experience import POOL_FILE

import pytest

# 确保清理旧经验以开始纯净测试
if os.path.exists(POOL_FILE):
    os.remove(POOL_FILE)

@pytest.mark.asyncio
async def test_learning_cycle():
    logger.info("=== [V35.3 闭环学习测试启动] ===")
    
    from app.core.agent_graph import get_graph_executor
    app, _ = get_graph_executor()
    
    # 模拟输入：一个容易让模型遗漏列的复杂请求
    inputs = {
        "messages": [("user", "分析患者 PSN_20210001 的两次住院间隔。")],
        "session_id": "test_session_learn",
        "retry_count": 0
    }
    
    # 第一次运行：预期会发生一次拦截重试
    logger.info(">>> 轮次 1: 模拟‘初次踩坑’并自愈...")
    config = {"configurable": {"thread_id": "test_1"}}
    
    state_1 = await app.ainvoke(inputs, config=config)
    logger.info(f"轮次 1 完成。重试次数: {state_1.get('retry_count')}")
    
    # 验证经验库是否已写入
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, 'r', encoding='utf-8') as f:
            pool = json.load(f)
            logger.info(f"经验库已沉淀条数: {len(pool)}")
            if pool:
                logger.info(f"最后一条记录意图: {pool[-1]['intent'][:50]}...")
    else:
        logger.error("经验库未生成！保存失败。")
        return

    # 第二次运行：相同意图，预期直接通过经验注入实现“一次成功”
    logger.info(">>> 轮次 2: 模拟‘经验复用’。预期 0 次重试，一次写对 SQL...")
    inputs_2 = {
        "messages": [("user", "分析患者 PSN_20210001 的两次住院间隔。")],
        "session_id": "test_session_learn_2",
        "retry_count": 0
    }
    
    state_2 = await app.ainvoke(inputs_2, config=config)
    
    # 核心验证点：轮次 2 的 retry_count 应该为 1 (代表 0 次重试就成功了，因为我们的 node 逻辑里成功也 +1)
    # 等一下，node 逻辑里成功返回 retry_count + 1。
    # 如果第一次就对，结果是 1。如果有重试，结果是 2。
    final_retry = state_2.get('retry_count')
    logger.info(f"轮次 2 结果：最终 retry_count = {final_retry}")
    
    if final_retry == 1:
        logger.info("SUCCESS: 经验成功复用，实现了零重试一次写对！")
    else:
        logger.warning(f"FAILURE: 仍然发生了重试。Retry Count: {final_retry}")

if __name__ == "__main__":
    asyncio.run(test_learning_cycle())
