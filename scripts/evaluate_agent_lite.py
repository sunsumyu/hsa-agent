import sys
import os
import json
import asyncio
from loguru import logger
from datetime import datetime
from dotenv import load_dotenv

# Ensure local imports work
sys.path.append(os.getcwd())

from app.agent_graph import get_graph_executor
from app.model_manager import model_manager
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

load_dotenv()

# --- 定价矩阵 (基于用户截图, 单位: 人民币/1k Tokens) ---
PRICE_MATRIX = {
    "doubao-pro-32k": {"input": 0.0008, "output": 0.0024},
    "doubao-2-pro": {"input": 0.0032, "output": 0.0096},
    "doubao-2-mini": {"input": 0.0002, "output": 0.0008},
    "deepseek-v3": {"input": 0.0020, "output": 0.0040},
    "glm-4": {"input": 0.0020, "output": 0.0040},
    "doubao-lite-1-6": {"input": 0.0003, "output": 0.0006},
    "gemma-4-31b-it": {"input": 0.0010, "output": 0.0020}, # 预设值
    "qwen-plus": {"input": 0.0040, "output": 0.0120},
    "qwen-turbo": {"input": 0.0010, "output": 0.0030},
    "qwen-max": {"input": 0.0200, "output": 0.0600},
    "gemini-1.5-flash": {"input": 0.0000, "output": 0.0000}, # 免费额度内
}

async def judge_response(input_text, actual_output, expected_output, retrieval_context):
    """Lite judge using Gemma instead of Qwen due to quota issues."""
    try:
        # 强制使用 Qwen-Turbo 作为裁判
        judge_llm, _ = model_manager.get_adaptive_llm(model_id="qwen-turbo")
    except Exception as e:
        logger.error(f"Failed to load judge LLM: {e}")
        return {"evidence_chain": 0, "numerical_precision": 0, "faithfulness": 0}
    
    prompt = f"""
    作为医保稽核最高监察官，请根据以下信息对 Agent 的稽核表现进行打分 (0-10 分):
    
    【用户问题】: {input_text}
    【检索到的事实依据】: {retrieval_context}
    【期望回答】: {expected_output}
    【Agent 实际回答】: {actual_output}
    
    评分极其严格准则:
    1. **证据链完整度 (Evidence Chain)**: 
       - 必须包含具体的：违规事实、涉案金额(￥)、政策依据条款、稽核处理建议。
       - **惩罚项**：如果 Agent 回复的是“阶段性审计评估”或“证据匮乏 (Scenario B)”，且【期望回答】中明显有具体的金额和事实，该项打分应低于 2 分。
    2. **数值精确度 (Numerical Precision)**: 
       - 回复中的金额、日期、ID 必须与事实或期望回答 100% 匹配。
    3. **业务专业度 (Faithfulness)**: 
       - 结论是否基于检索到的物理事实，禁止出现“SQL报错”或“权限不足”等技术性接口话术。

    请严格以 JSON 格式输出，不要有额外解释。示例: {{"evidence_chain": 8.5, "numerical_precision": 10.0, "faithfulness": 9.0}}
    """
    
    import asyncio
    try:
        # 增加 45 秒硬超时，防止裁判节点挂起导致全盘皆输
        res = await asyncio.wait_for(judge_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
        # Clean potential markdown or extra text
        content = res.content.strip()
        if "{" in content and "}" in content:
            clean_res = content[content.find("{"):content.rfind("}")+1]
            return json.loads(clean_res)
        return {"evidence_chain": 0, "numerical_precision": 0, "faithfulness": 0}
    except asyncio.TimeoutError:
        logger.error("Judge timed out (45s) - skipping score for this case")
        return {"evidence_chain": 0, "numerical_precision": 0, "faithfulness": 0}
    except Exception as e:
        logger.error(f"Judge failed: {e}")
        return {"evidence_chain": 0, "numerical_precision": 0, "faithfulness": 0}

async def run_evaluation_lite(model_id: str = "qwen-turbo", max_cases: int = 10):
    logger.info(f"🚀 启动增强版对比测试 [模型: {model_id or '自动选择'}, 规模: {max_cases} 案]...")
    
    dataset_path = "tests/eval/golden_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)[:max_cases]

    executor, resolved_model_id = get_graph_executor(model_id=model_id)
    
    stats = {
        "model_id": resolved_model_id,
        "cases": [],
        "total_tokens": {"input": 0, "output": 0},
        "total_cost": 0.0
    }

    price = PRICE_MATRIX.get(resolved_model_id, {"input": 0, "output": 0})

    for i, item in enumerate(golden_data):
        input_text = item["input"]
        logger.info(f"[{resolved_model_id}] Case {i+1}/{len(golden_data)}: {input_text[:30]}...")
        
        try:
            state = {"messages": [HumanMessage(content=input_text)], "model_id": resolved_model_id}
            response = await executor.ainvoke(state)
            messages = response.get("messages", [])
            actual_output = ""
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content.strip():
                    actual_output = msg.content
                    break
            
            # 最后的真相保底：如果消息列表全是空的，则直接提取 findings 或 ToolMessage
            if not actual_output:
                facts = response.get("findings", [])
                
                # 深度打捞：优先寻找包含“SQL 执行结果”或“明细”的内容
                relevant_msgs = []
                for msg in reversed(messages):
                    if isinstance(msg, ToolMessage):
                        content = msg.content
                        if "Result" in content or "明细" in content or "Row" in content:
                            relevant_msgs.append(f"审计证据抓取: {content[:400]}")
                
                if not relevant_msgs:
                    # 退而求其次，寻找表结构发现
                    for msg in reversed(messages):
                        if isinstance(msg, ToolMessage):
                            relevant_msgs.append(f"工具探测事实: {msg.content[:200]}")
                
                if not facts and relevant_msgs:
                    facts = relevant_msgs[:5]
                
                if facts:
                    actual_output = "### 🚩 审计疑点分析 (物理打捞汇总)\n" + "\n".join(facts)
            
            logger.info(f"--- Agent Response (First 100 chars) ---\n{actual_output[:100]}\n---")
            
            # 统计本次调用 Token (兼容多种元数据格式)
            case_tokens = {"input": 0, "output": 0}
            for msg in messages:
                if isinstance(msg, AIMessage):
                    # 1. 尝试标准 usage_metadata
                    if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                        case_tokens["input"] += msg.usage_metadata.get("input_tokens", 0)
                        case_tokens["output"] += msg.usage_metadata.get("output_tokens", 0)
                    # 2. 尝试 response_metadata (针对某些旧版或特定 Provider)
                    elif hasattr(msg, "response_metadata") and msg.response_metadata:
                        usage = msg.response_metadata.get("token_usage", {})
                        if not usage:
                            usage = msg.response_metadata.get("usage", {})
                        case_tokens["input"] += usage.get("prompt_tokens", usage.get("input_tokens", 0))
                        case_tokens["output"] += usage.get("completion_tokens", usage.get("output_tokens", 0))

            # 计算成本 (人民币)
            case_cost = (case_tokens["input"] / 1000 * price["input"]) + (case_tokens["output"] / 1000 * price["output"])
            
            stats["total_tokens"]["input"] += case_tokens["input"]
            stats["total_tokens"]["output"] += case_tokens["output"]
            stats["total_cost"] += case_cost

            # 获取专家评分 (打印 raw 判定结果以排查)
            logger.info("Requesting Judge score...")
            scores = await judge_response(input_text, actual_output, item.get("expected_output"), "")
            logger.info(f"CAPTURED CONCLUSION: {actual_output[:100]}...")
            scores["cost"] = round(case_cost, 4)
            scores["tokens"] = case_tokens["input"] + case_tokens["output"]
            scores["actual_output"] = actual_output
            
            stats["cases"].append(scores)
            logger.success(f"Case {i+1} Result -> Tokens: [In:{case_tokens['input']}|Out:{case_tokens['output']}], Cost: ￥{scores['cost']}, Score: {scores['evidence_chain']}")

            # [实时同步] 每跑完一个案例即保存一次，展示真实判词
            raw_summary = []
            for idx, c in enumerate(stats["cases"]):
                raw_summary.append({
                    "case_id": idx + 1,
                    "model": resolved_model_id,
                    "score": c["evidence_chain"],
                    "conclusion": c.get("actual_output", "无结论")
                })
            with open("data/raw_audit_results.json", "w", encoding="utf-8") as f:
                json.dump(raw_summary, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Case {i+1} Crash: {e}")
            import traceback
            logger.error(traceback.format_exc())
            stats["cases"].append({"evidence_chain": 0, "numerical_precision": 0, "faithfulness": 0, "cost": 0, "tokens": 0})

    # 汇总
    if stats["cases"]:
        stats["summary"] = {
            "avg_evidence_chain": sum(c["evidence_chain"] for c in stats["cases"]) / len(stats["cases"]),
            "avg_numerical_precision": sum(c["numerical_precision"] for c in stats["cases"]) / len(stats["cases"]),
            "avg_faithfulness": sum(c["faithfulness"] for c in stats["cases"]) / len(stats["cases"]),
            "avg_cost_per_case": stats["total_cost"] / len(stats["cases"]),
            "total_cost": stats["total_cost"],
            "avg_input_tokens": stats["total_tokens"]["input"] / len(stats["cases"]),
            "avg_output_tokens": stats["total_tokens"]["output"] / len(stats["cases"]),
            "avg_total_tokens": (stats["total_tokens"]["input"] + stats["total_tokens"]["output"]) / len(stats["cases"])
        }
    
    return stats

async def run_comparison_benchmark(target_models=None):
    if target_models is None:
        target_models = ["qwen-turbo", "gemma-4-31b-it"]
    
    all_results = []
    
    for mid in target_models:
        try:
            stats = await run_evaluation_lite(model_id=mid, max_cases=10)
            all_results.append(stats)
            
            # 记录详细的原始审计事实 (模型隔离存储)
            raw_results = []
            for i, c in enumerate(stats["cases"]):
                raw_results.append({
                    "case_id": i+1,
                    "model": mid,
                    "score": c["evidence_chain"],
                    "conclusion": c.get("actual_output", "无结论")
                })
            
            file_name = f"data/raw_audit_results_{mid.replace('-', '_')}.json"
            with open(file_name, "w", encoding="utf-8") as f:
                json.dump(raw_results, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"模型 {mid} 测试失败: {e}")

    # 生成对比报表 (仅在跑多模型时生成)
    if len(all_results) > 0:
        report = f"# 医保稽核 Agent 性能-成本对比报告\n"
        report += f"> 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 样本数: 10\n\n"
        report += "| 模型 | 综合评分 | 证据链 | 数值精度 | 平均成本(RMB) | 总成本 | 平均全链路Tokens (In/Out) |\n"
        report += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        
        for r in all_results:
            s = r["summary"]
            total_score = (s["avg_evidence_chain"] + s["avg_numerical_precision"] + s["avg_faithfulness"]) / 3
            report += f"| {r['model_id']} | **{total_score:.2f}** | {s['avg_evidence_chain']:.2f} | {s['avg_numerical_precision']:.2f} | ￥{s['avg_cost_per_case']:.4f} | ￥{s['total_cost']:.4f} | {s['avg_total_tokens']:.0f} ({s['avg_input_tokens']:.0f} / {s['avg_output_tokens']:.0f}) |\n"
        
        with open("data/benchmark_comparison_report.md", "w", encoding="utf-8") as f:
            f.write(report)
        logger.success("对比测试完成！报告已保存至 data/benchmark_comparison_report.md")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="医保稽核 Agent 评估工具")
    parser.add_argument("--model", type=str, help="指定测试模型 ID (如 qwen-turbo)")
    parser.add_argument("--compare", action="store_true", help="运行预设的多模型对比")
    parser.add_argument("--cases", type=int, default=10, help="测试案例数量")
    
    args = parser.parse_args()
    
    if args.compare:
        asyncio.run(run_comparison_benchmark())
    elif args.model:
        asyncio.run(run_evaluation_lite(model_id=args.model, max_cases=args.cases))
    else:
        # 默认行为：跑单模型 Qwen
        asyncio.run(run_evaluation_lite(model_id="qwen-turbo", max_cases=args.cases))
