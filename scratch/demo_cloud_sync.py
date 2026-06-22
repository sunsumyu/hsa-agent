import asyncio
import sys
import os
from loguru import logger

# 路径修复
sys.path.append(os.getcwd())

from app.infra.usage_tracker import usage_tracker
from app.core.quota.manager import quota_manager

async def run_demo():
    logger.info("🚀 启动企业级配额云端校准演示...")
    
    # 1. 执行全量同步 (模拟调用云端接口)
    await quota_manager.sync_all()
    
    # 2. 模拟从云端获取到了真实数据 (假设本地估算 10w，云端显示已用 15w)
    # 以 doubao-pro-32k 为例
    model_id = "doubao-pro-32k"
    real_usage = 150000 
    
    logger.info(f"📡 发现云端真实用量数据: {real_usage} Tokens")
    
    # 3. 执行物理校准
    usage_tracker.calibrate_usage(model_id, real_usage)
    
    # 4. 刷新看板数据
    import subprocess
    subprocess.run(["python", "scratch/export_dashboard_data.py"])
    
    logger.success("✨ 云端校准演示完成，仪表盘已实时更新预测数据。")

if __name__ == "__main__":
    asyncio.run(run_demo())
