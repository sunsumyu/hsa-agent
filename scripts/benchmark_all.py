import asyncio
import json
import os
import sys
import time
from loguru import logger
from tabulate import tabulate
from langchain_core.messages import HumanMessage
from app.core.agent_graph import get_graph_executor

# Setup for UTF-8 and Projekt Root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.eval.metrics import HSANumericalPrecisionMetric

async def evaluate_model(model_id: str, test_cases: list):
    logger.info(f"--- 正在评测模型: {model_id} ---")
    executor, resolved_id = get_graph_executor(model_id=model_id)
    
    # 初始化专家级指标
    precision_metric = HSANumericalPrecisionMetric()
    
    results = []
    for i, case in enumerate(test_cases):
        start_time = time.time()
        try:
            state = {
                "messages": [HumanMessage(content=case["input"])],
                "model_id": model_id
            }
            # LangGraph invoke
            response = executor.invoke(state)
            latency = time.time() - start_time
            
            actual_output = response["messages"][-1].content
            expected = str(case.get("expected_output", ""))
            
            # 使用专业指标进行打分
            score_res = precision_metric.measure(actual_output, expected)
            score = float(score_res) if score_res is not None else 0.0
            
            results.append({
                "Case": i + 1,
                "Latency": f"{latency:.2f}s",
                "Score": score,
                "Status": "✅" if score > 0 else "⚠️"
            })
            logger.info(f"  [案例 {i+1}] 得分: {score:.2f}, 耗时: {latency:.2f}s")
        except Exception as e:
            logger.error(f"模型 {model_id} 案例 {i+1} 失败: {e}")
            results.append({
                "Case": i + 1,
                "Latency": "N/A",
                "Score": 0,
                "Status": f"❌ {str(e)[:20]}"
            })
            
    # 计算平均分
    avg_score = sum(r["Score"] for r in results) / len(results) if results else 0
    avg_latency = sum(float(r["Latency"][:-1]) for r in results if r["Latency"] != "N/A") / len(results) if results else 0
    
    return {
        "Model": model_id,
        "Avg Score": f"{avg_score:.2f}",
        "Avg Latency": f"{avg_latency:.2f}s",
        "Success": f"{sum(1 for r in results if r['Status'] == '✅')}/{len(results)}"
    }

async def main():
    # 1. 加载数据集
    dataset_path = os.path.join(project_root, "tests", "eval", "golden_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    # 2. 待测模型列表 (基于 llm_providers.json)
    providers_path = os.path.join(project_root, "app", "llm_providers.json")
    with open(providers_path, "r", encoding="utf-8") as f:
        providers = json.load(f)
    
    model_ids = list(providers.keys())
    
    # 3. 执行对比测试
    leaderboard = []
    for mid in model_ids:
        report = await evaluate_model(mid, golden_data)
        leaderboard.append(report)
        
    # 4. 保存结果 (提前保存，防止打印报错导致数据丢失)
    os.makedirs("data", exist_ok=True)
    with open("data/comparative_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

    # 5. 输出结果 (配置为 UTF-8 输出)
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("\n" + "="*60)
    print("医保稽核 Multi-Agent 架构模型对比天梯")
    print("="*60)
    if leaderboard:
        print(tabulate(leaderboard, headers="keys", tablefmt="github"))
    else:
        print("未收集到有效评测数据。")
    print("="*60)
    
if __name__ == "__main__":
    asyncio.run(main())
