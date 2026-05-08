import time
import asyncio
import os
import sys
import json
import statistics
from datetime import datetime

# 注入 PYTHONPATH
sys.path.append("e:/chain/hsa-agent-python")
os.chdir("e:/chain/hsa-agent-python")

from app.agent_graph import get_graph_executor
from app.semantic_layer import get_embedding_model
from app.usage_tracker import usage_tracker

# 10 个专业审计测试用例
TEST_SUITE = [
    {"id": "QA-01", "cat": "统计", "q": "2021年总医疗费用排名前5的医院及其总费用？"},
    {"id": "QA-02", "cat": "类型", "q": "统计各定点医疗机构在2021年的总住院天数（求和）。"},
    {"id": "QA-03", "cat": "个案", "q": "查找 psn_no 为 'P12345' 的患者在 2021 年的所有就医记录。"},
    {"id": "QA-04", "cat": "高级", "q": "筛选 2021 年内，单次住院费用超过 10 万元的异常病例。"},
    {"id": "QA-05", "cat": "逻辑", "q": "分析 2021 年是否存在同一个患者在同一天多次入院的情况？"},
    {"id": "QA-06", "cat": "统计", "q": "按病种（diag_name）统计 2021 年度的统筹基金支付总额。"},
    {"id": "QA-07", "cat": "类型", "q": "查询 2021 年平均单次就医费用最高的 3 个科室。"},
    {"id": "QA-08", "cat": "复合", "q": "2021年，哪些医院的药费占比超过了总费用的 50%？"},
    {"id": "QA-09", "cat": "性能", "q": "全量扫描 2021 年所有的跨省异地就医记录并按金额排序。"},
    {"id": "QA-10", "cat": "容错", "q": "查询一个不存在的年份（如 1990 年）看系统的鲁棒性反馈。"}
]

async def monitor_node_latency(case):
    executor, _ = get_graph_executor()
    stats = {
        "case_id": case["id"],
        "category": case["cat"],
        "start_time": time.time(),
        "nodes": {},
        "total_tokens": 0,
        "retries": 0,
        "success": False
    }
    
    inputs = {"messages": [("user", case["q"])], "retry_count": 0}
    
    last_node_start = time.time()
    try:
        async for event in executor.astream(inputs, stream_mode="updates"):
            curr_time = time.time()
            node_name = list(event.keys())[0]
            latency = curr_time - last_node_start
            stats["nodes"][node_name] = stats["nodes"].get(node_name, 0) + latency
            last_node_start = curr_time
            
            # 记录重试
            if "retry_count" in event[node_name]:
                stats["retries"] = event[node_name]["retry_count"]
                
        stats["end_time"] = time.time()
        stats["total_latency"] = stats["end_time"] - stats["start_time"]
        stats["success"] = True
    except Exception as e:
        stats["error"] = str(e)
        stats["total_latency"] = time.time() - stats["start_time"]
        
    return stats

async def run_professional_benchmark():
    print(f"🚀 [Industrial Benchmark] Starting Enterprise Grade Test Suite (N={len(TEST_SUITE)})...")
    # 预热
    get_embedding_model()
    
    full_report = []
    for case in TEST_SUITE:
        res = await monitor_node_latency(case)
        full_report.append(res)
        print(f"✔ Completed {case['id']} | Latency: {res['total_latency']:.2f}s | Success: {res['success']}")

    # 数据汇总与分析
    with open("data/professional_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
    
    print("\n📈 [Benchmark] Data Collection Finished. Generating Final Analysis...")

if __name__ == "__main__":
    asyncio.run(run_professional_benchmark())
