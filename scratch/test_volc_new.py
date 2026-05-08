import asyncio
import os
import sys

# 环境初始化
sys.path.append(os.getcwd())

from app.model_manager import model_manager

async def test_new_endpoints():
    print(">>> [算力拨测] 正在验证新接入的火山引擎 Smart Router 节点...")
    results = await model_manager.run_health_check()
    print(f"\n✅ 拨测完成! 详情: {results}")

if __name__ == "__main__":
    asyncio.run(test_new_endpoints())
