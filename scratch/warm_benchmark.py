import time
import asyncio
import os
import sys

# 注入 PYTHONPATH
sys.path.append("e:/chain/hsa-agent-python")
os.chdir("e:/chain/hsa-agent-python")

from app.agent_graph import get_graph_executor
from app.semantic_layer import get_embedding_model

async def run_benchmark():
    print("🔥 [WARM-UP] 正在预热引擎：加载模型与语义索引...")
    start_warm = time.time()
    # 强制触发模型加载
    get_embedding_model()
    print(f"✅ 引擎预热完成，耗时: {time.time() - start_warm:.2f}s")

    executor, _ = get_graph_executor()
    
    test_cases = [
        {"id": "T1", "query": "2021年度总费用排名前三的医院？"},
        {"id": "T2", "query": "统计各机构2021年的平均住院天数。"}
    ]
    
    for case in test_cases:
        print(f"\n🚀 [RUNNING] Case {case['id']}: {case['query']}")
        start_case = time.time()
        inputs = {"messages": [("user", case['query'])], "retry_count": 0}
        
        async for event in executor.astream(inputs, stream_mode="values"):
            # 持续监听流，直到结束
            pass
            
        print(f"✅ Case {case['id']} 完成 | 耗时: {time.time() - start_case:.2f}s")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
