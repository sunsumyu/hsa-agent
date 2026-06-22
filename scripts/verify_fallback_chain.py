import json
import os
from app.infra.usage_tracker import usage_tracker
from app.infra.model_manager import model_manager
from loguru import logger

def verify_fallback_logic():
    stats_path = "data/usage_stats.json"
    
    # 模拟场景：
    # 1. doubao-2-pro 已经用完 (限额 500,000, 已用 500,001)
    # 2. doubao-2-mini 还有额度 (限额 500,000, 已用 10,000)
    
    mock_stats = {
        "daily_limit": 10000000,
        "today": usage_tracker.stats["today"],
        "daily_usage": {
            "doubao-2-pro": 500001,
            "doubao-2-mini": 10000
        },
        "model_limits": {
            "doubao-2-pro": 500000,
            "doubao-2-mini": 500000
        },
        "total_usage": {}
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(mock_stats, f, indent=2)
    
    # 强制重载
    usage_tracker.stats = usage_tracker._load_stats()
    
    logger.info("--- 测试：单模型回退逻辑 ---")
    logger.info(f"预期行为：跳过已超限的 doubao-2-pro，尝试加载 doubao-2-mini")
    
    # 注意：由于 doubao-2-mini 此时 model_name 是 YOUR_ENDPOINT_ID，
    # _create_llm 可能会因为无效 ID 失败，但我们要验证的是 get_adaptive_llm 
    # 是否正确过滤了第一个模型并尝试了第二个。
    
    try:
        # 重载配置
        model_manager.providers = model_manager._load_config()
        
        # 尝试构建执行链
        llm_chain, node_name = model_manager.get_adaptive_llm()
        logger.info(f"构网成功！主控节点锁定为: {node_name}")
        
    except Exception as e:
        # 如果报错，检查错误信息是否包含“跳过”
        logger.info(f"执行链构建结果: {e}")

    # 打印日志检查
    logger.info("请检查上方日志，确认是否出现了 '跳过模型 doubao-2-pro' 的警告。")

if __name__ == "__main__":
    verify_fallback_logic()
