import time
import asyncio
import os

# 物理切换工作目录以确保相对路径配置文件 (llm_providers.json) 被正确加载
os.chdir("e:/chain/hsa-agent-python")
from app.agent_graph import get_graph_executor

async def run_speed_test():
    query = "查询 2021 年度，总医疗费用排名前三的定点医疗机构。"
    print(f"🚀 [Speed Test] Starting Case 2: {query}")
    
    start_time = time.time()
    # 初始化执行器
    executor, model_name = get_graph_executor()
    
    inputs = {"messages": [("user", query)], "retry_count": 0}
    
    async for event in executor.astream(inputs, stream_mode="values"):
        # 实时打印节点流转以观察感知时延
        current_time = time.time() - start_time
        print(f"[{current_time:.2f}s] Graph Event Received...")
        
    end_time = time.time()
    total_latency = end_time - start_time
    print(f"\n✅ [Test Complete] Total Latency: {total_latency:.2f}s")

if __name__ == "__main__":
    asyncio.run(run_speed_test())
