import sys
import os
# 添加当前目录到路径
sys.path.append(os.getcwd())

from app.usage_tracker import usage_tracker
from app.model_manager import model_manager
from loguru import logger

def test_pydantic_migration():
    logger.info(">>> 开始验证 Pydantic 架构迁移...")
    
    # 1. 验证模型加载
    models = model_manager.get_model_list()
    assert len(models) > 0, "模型注册表加载失败"
    logger.success(f"成功加载 {len(models)} 个模型配置。")
    
    # 2. 验证统计数据加载
    stats = usage_tracker.stats
    logger.info(f"当前统计日期: {stats.today}")
    assert stats.today.startswith("2026"), "日期解析异常"
    
    # 3. 验证用量记录
    test_model = models[0]["id"]
    initial_usage = stats.daily_usage.get(test_model, 0)
    logger.info(f"测试模型 {test_model} 初始用量: {initial_usage}")
    
    usage_tracker.record_usage(test_model, 1000, 500)
    new_usage = usage_tracker.stats.daily_usage.get(test_model)
    logger.success(f"测试模型 {test_model} 更新后用量: {new_usage}")
    assert new_usage == initial_usage + 1500, "用量累加失败"
    
    # 4. 验证算力选择
    llm, node_name = model_manager.get_fast_model()
    logger.success(f"成功锁定推演节点: {node_name}")
    
    logger.success(">>> Pydantic 架构迁移验证通过！")

if __name__ == "__main__":
    test_pydantic_migration()
