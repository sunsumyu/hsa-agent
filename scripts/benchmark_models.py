import os
import sys
import asyncio
import json
from loguru import logger

# [核心补丁] 确保项目根目录在 PYTHONPATH 中，以便正确加载 scripts 模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"项目根路径已注入: {project_root}")

from datetime import datetime
from tabulate import tabulate
from scripts.evaluate_agent import run_evaluation

async def run_benchmark():
    logger.info("🚀 启动医保稽核 Agent 多模型全量基准测试...")
    
    # 1. 尝试从配置加载模型清单
    config_path = "app/llm_providers.json"
    if not os.path.exists(config_path):
        logger.error(f"配置文件不存在: {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        providers = json.load(f)
    
    model_ids = list(providers.keys())
    logger.info(f"探测到 {len(model_ids)} 个待测算力节点: {model_ids}")

    all_stats = []
    
    # 2. 依次轮询评测
    for model_id in model_ids:
        try:
            # 运行单模型评测
            eval_result = await run_evaluation(model_id=model_id)
            
            if eval_result and "results" in eval_result:
                # 提取指标平均分
                evaluation_result = eval_result["results"]
                total_test_results = evaluation_result.test_results if hasattr(evaluation_result, 'test_results') else []
                
                # 注意：DeepEval 3.x 结果对象结构解析
                summary = {
                    "Model": eval_result["model_id"],
                    "Status": "✅ Success",
                    "Evidence Chain": "N/A",
                    "Faithfulness": "N/A",
                    "Numerical Precision": "N/A",
                    "Pass Rate": "0%"
                }
                
                # 统计通过率和指标分
                passed = 0
                total = 0
                evidence_score = 0
                faithfulness_score = 0
                precision_score = 0
                relevance_score = 0
                
                for res in total_test_results:
                    total += 1
                    if res.success:
                        passed += 1
                    
                    # 适配 DeepEval 3.x: 使用 metrics_data 而不是 metrics 属性
                    metrics_list = res.metrics_data if hasattr(res, 'metrics_data') else []
                    for m_data in metrics_list:
                        # MetricData 对象通常有 name 和 score 属性
                        name = m_data.name if hasattr(m_data, 'name') else str(m_data)
                        score = m_data.score if hasattr(m_data, 'score') else 0
                        
                        if "Evidence Chain" in name:
                            evidence_score += score
                        elif "数值精确度" in name:
                            precision_score += score
                        elif "Faithfulness" in name:
                            faithfulness_score += score
                        elif "Answer Relevance" in name:
                            relevance_score += score
                
                if total > 0:
                    summary["Evidence Chain"] = f"{evidence_score/total:.2f}"
                    summary["Faithfulness"] = f"{faithfulness_score/total:.2f}"
                    summary["Numerical Precision"] = f"{precision_score/total:.2f}"
                    summary["Pass Rate"] = f"{(passed/total)*100:.1f}%"
                
                all_stats.append(summary)
            else:
                all_stats.append({
                    "Model": model_id,
                    "Status": "❌ Failed/Skipped",
                    "Evidence Chain": "-",
                    "Numerical Precision": "-",
                    "Pass Rate": "-"
                })
        except Exception as e:
            logger.error(f"模型 {model_id} 评测崩溃: {e}")
            all_stats.append({
                "Model": model_id,
                "Status": "💥 Crash",
                "Evidence Chain": "-",
                "Numerical Precision": "-",
                "Pass Rate": "-"
            })

    # 3. 输出汇总表格
    print("\n" + "="*80)
    print(f"🏆 医保稽核 Agent 多模型能力天梯 (Benchmark Report) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*80)
    if all_stats:
        table_output = tabulate(all_stats, headers="keys", tablefmt="github")
        print(table_output)
        
        # 4. 保存为文件供后续查看
        report_path = "data/benchmark_report.md"
        os.makedirs("data", exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 医保稽核 Agent 基准测试报告\n")
            f.write(f"> 生成时间: {datetime.now().isoformat()}\n\n")
            f.write(table_output)
            f.write("\n\n---\n*注：证据链评分由 Qwen-Max 统一裁定。*")
        
        logger.success(f"基准测试完成！详细报告已保存至: {report_path}")
    else:
        logger.warning("未收集到任何有效评测数据。")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
