import time
import asyncio
import os
import json
from datetime import datetime

# 物理切换工作目录以确保配置加载
os.chdir("e:/chain/hsa-agent-python")
from app.agent_graph import get_graph_executor

# 测试用例定义
BENCHMARK_CASES = [
    {"id": "C1", "name": "简单统计", "query": "2021年总医疗费用最高的3家医院。"},
    {"id": "C2", "name": "类型敏感", "query": "统计 2021 年各机构的平均住院天数。"},
    {"id": "C3", "name": "多维分析", "query": "分析 2021 年门诊统筹基金支出排名前五的病种。"},
    {"id": "C4", "name": "高级算子", "query": "扫描 2021 年内变异指数 (VIX) 超过 1.5 的高风险住院病例。"}
]

async def run_single_test(case):
    print(f"\n>>> [Benchmark] Running {case['id']}: {case['name']}...")
    executor, _ = get_graph_executor()
    
    start_time = time.time()
    node_timings = []
    last_event_time = start_time
    
    inputs = {"messages": [("user", case['query'])], "retry_count": 0}
    final_state = None
    
    try:
        async for event in executor.astream(inputs, stream_mode="values"):
            current_time = time.time()
            duration = current_time - last_event_time
            last_event_time = current_time
            
            # 记录简单的节点流转（实际中可以解析更复杂的 event）
            node_timings.append(duration)
            final_state = event
            
        total_latency = time.time() - start_time
        
        # 提取关键指标
        retry_count = final_state.get("retry_count", 0)
        sql_validated = final_state.get("sql_validated", False)
        
        return {
            "id": case['id'],
            "name": case['name'],
            "latency": total_latency,
            "retries": retry_count,
            "fast_track": sql_validated and retry_count == 0,
            "status": "PASS" if retry_count < 3 else "FAIL"
        }
    except Exception as e:
        return {
            "id": case['id'],
            "name": case['name'],
            "latency": time.time() - start_time,
            "error": str(e),
            "status": "ERROR"
        }

async def run_full_benchmark():
    results = []
    for case in BENCHMARK_CASES:
        res = await run_single_test(case)
        results.append(res)
    
    # 保存结果
    with open("data/benchmark_full_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n✅ Benchmark Complete. Generating Report...")

if __name__ == "__main__":
    asyncio.run(run_full_benchmark())
