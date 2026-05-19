import asyncio
import os
import sys
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())

from app.infra.model_manager import model_manager
from app.infra.endpoint_pool_manager import endpoint_pool_manager

async def test_pooling_logic():
    print("\n>>> [池化架构测试] 正在模拟多角色寻址...")
    
    roles = ["planner_heavy", "coder", "reporter"]
    
    for role in roles:
        print(f"\n--- 模拟角色: {role} ---")
        # 连续调用 3 次，观察加权分配结果
        for i in range(3):
            _, ep_id = model_manager.get_llm_by_role(role)
            print(f"第 {i+1} 次选中接入点: {ep_id}")

    print("\n>>> [平滑切换测试] 模拟节点故障...")
    # 模拟 doubao-pro-32k 挂了
    target_ep = "doubao-pro-32k"
    endpoint_pool_manager.record_failure(target_ep, "Manual Simulation Error 500")
    
    print(f"已手动将 {target_ep} 放入冷却期。")
    print("再次请求高质量池任务...")
    _, next_ep = model_manager.get_llm_by_role("planner_heavy")
    print(f"自动平滑切换到: {next_ep}")

if __name__ == "__main__":
    asyncio.run(test_pooling_logic())
