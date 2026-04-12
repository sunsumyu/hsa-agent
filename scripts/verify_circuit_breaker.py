import json
from app.usage_tracker import usage_tracker
from app.model_manager import model_manager
from loguru import logger

def verify_circuit_breaker():
    stats_path = "data/usage_stats.json"
    limit = 1000
    
    # 模拟用量已达到上限
    mock_stats = {
        "daily_limit": limit,
        "today": usage_tracker.stats["today"],
        "daily_usage": {"test-model": limit + 100},
        "total_usage": {"test-model": limit + 100}
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(mock_stats, f, indent=2)
    
    # 重新加载
    usage_tracker.stats = usage_tracker._load_stats()
    
    logger.info(f"验证熔断器：当前设定用量 {sum(usage_tracker.stats['daily_usage'].values())}, 限额 {limit}")
    
    try:
        logger.info("尝试获取模型...")
        model_manager.get_adaptive_llm(model_id="any-model")
        logger.error("失败：熔断器未能拦截请求！")
    except RuntimeError as e:
        if "Token 消耗已达上限" in str(e):
            logger.success(f"验证成功：熔断器已拦截请求并报错: {e}")
        else:
            logger.error(f"失败：捕获到错误但不是熔断错误: {e}")
    except Exception as e:
        logger.error(f"失败：捕获到未知异常: {e}")
    finally:
        # 重置回默认限额，但不清空历史，方便用户查看
        mock_stats["daily_limit"] = 1000000
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(mock_stats, f, indent=2)

if __name__ == "__main__":
    verify_circuit_breaker()
