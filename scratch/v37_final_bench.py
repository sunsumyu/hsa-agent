import time
import asyncio
import os
import sys
import json
import re

# 注入 PYTHONPATH
sys.path.append("e:/chain/hsa-agent-python")
os.chdir("e:/chain/hsa-agent-python")

from app.agent_graph import get_graph_executor
from app.semantic_layer import get_embedding_model
from app.usage_tracker import usage_tracker

# 10 个专业审计测试用例（覆盖全维度）
TEST_SUITE = [
    {"id": "QA-01", "dim": "效能/统计", "q": "2021年总医疗费用排名前5的医院及其总费用？"},
    {"id": "QA-02", "dim": "质量/类型", "q": "统计各定点医疗机构在2021年的总住院天数（求和）。"},
    {"id": "QA-03", "dim": "质量/个案", "q": "查询 psn_no 为 'P12345' 的患者在 2021 年的所有就医记录明细。"},
    {"id": "QA-04", "dim": "安全/资源", "q": "筛选 2021 年内，单次住院费用超过 10 万元的异常病例。"},
    {"id": "QA-05", "dim": "稳健/逻辑", "q": "分析 2021 年是否存在同一个患者在同一天多次入院的情况？"},
    {"id": "QA-06", "dim": "深度/业务", "q": "按病种（diag_name）统计 2021 年度的统筹基金支付总额。"},
    {"id": "QA-07", "dim": "效能/性能", "q": "查询 2021 年平均单次就医费用最高的 3 个科室。"},
    {"id": "QA-08", "dim": "安全/脱敏", "q": "导出 2021 年药费占比超过 50% 的所有患者名单（含 psn_no）。"},
    {"id": "QA-09", "dim": "质量/语义", "q": "全量扫描 2021 年所有的跨省异地就医记录并按金额排序。"},
    {"id": "QA-10", "dim": "稳健/鲁棒", "q": "查询一个不存在的年份（如 1990 年）看系统的降级反馈。"}
]

async def run_final_benchmark():
    print(f"🚀 [FINAL-BENCHMARK] 开始执行 V37.0 全维度标准测试 (N={len(TEST_SUITE)})...")
    
    # 预热常驻模型
    get_embedding_model()
    
    results = []
    executor, _ = get_graph_executor()
    
    for case in TEST_SUITE:
        print(f"\n📡 [TESTING] {case['id']} | {case['dim']}...")
        start_time = time.time()
        
        inputs = {"messages": [("user", case['q'])], "retry_count": 0}
        final_state = None
        
        try:
            # 记录节点时延
            node_times = {}
            last_ts = start_time
            
            async for event in executor.astream(inputs, stream_mode="updates"):
                curr_ts = time.time()
                node_name = list(event.keys())[0]
                node_times[node_name] = node_times.get(node_name, 0) + (curr_ts - last_ts)
                last_ts = curr_ts
                final_state = event[node_name]
            
            total_latency = time.time() - start_time
            
            # 抽取关键指标
            res = {
                "id": case['id'],
                "dimension": case["dim"],
                "query": case["q"],
                "latency": total_latency,
                "node_distribution": node_times,
                "retries": final_state.get("retry_count", 0) if final_state else 0,
                "sql": final_state.get("sql_query", "N/A") if final_state else "N/A",
                "success": total_latency < 30 and final_state.get("retry_count", 0) < 3 if final_state else False
            }
            results.append(res)
            print(f"✅ {case['id']} 完成 | 耗时: {total_latency:.2f}s | SQL一次通过: {res['retries'] == 0}")
            
        except Exception as e:
            print(f"❌ {case['id']} 失败: {e}")
            results.append({"id": case['id'], "error": str(e), "success": False})

    # 保存原始数据供分析
    with open("data/v37_final_benchmark_raw.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n📈 [DATA-COLLECTED] 原始数据已固化。正在准备分析白皮书...")

if __name__ == "__main__":
    asyncio.run(run_final_benchmark())
