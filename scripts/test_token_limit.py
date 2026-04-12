import os
import json
import asyncio
from loguru import logger
from app.usage_tracker import usage_tracker
from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage

async def test_limit():
    # 1. 设置一个极低的阈值进行测试
    stats_path = "data/usage_stats.json"
    limit = 500
    
    with open(stats_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    original_limit = data.get("daily_limit", 1000000)
    data["daily_limit"] = limit
    # 清空今日用量以便测试
    data["daily_usage"] = {}
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    # 刷新内存中的 usage_tracker
    usage_tracker.stats = usage_tracker._load_stats()
    
    logger.info(f"测试开始：已将每日限额设为 {limit} tokens")
    
    executor, model_id = get_graph_executor(model_id="qwen-plus")
    state = {"messages": [HumanMessage(content="你好，请介绍一下你自己")], "model_id": model_id}
    
    try:
        logger.info("尝试第一次调用...")
        res = executor.invoke(state)
        logger.success("第一次调用成功！")
        
        # 检查当前用量
        is_safe, current, limit = usage_tracker.check_limit()
        logger.info(f"当前用量: {current}/{limit}")
        
        logger.info("尝试第二次调用（预期触发熔断）...")
        res2 = executor.invoke(state)
        logger.error("错误：第二次调用居然成功了，熔断逻辑可能失效。")
        
    except RuntimeError as e:
        if "Token 消耗已达上限" in str(e):
            logger.success(f"成功触发熔断机制: {e}")
        else:
            logger.error(f"捕获到意外错误: {e}")
    except Exception as e:
        logger.error(f"发生异常: {e}")
    finally:
        # 恢复限额
        data["daily_limit"] = original_limit
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.info("已恢复原始限额配置。")

if __name__ == "__main__":
    # 确保 data 目录和初始统计文件存在
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists("data/usage_stats.json"):
        with open("data/usage_stats.json", 'w') as f:
            json.dump({"daily_limit": 1000000, "today": "", "daily_usage": {}, "total_usage": {}}, f)
            
    asyncio.run(test_limit())
