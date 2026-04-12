import os
import sys
import pydantic
from loguru import logger

# [核心补丁] 确保项目根目录在 PYTHONPATH 中，以便正确加载 tests 模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    logger.info(f"项目根路径已注入: {project_root}")

# [核心补丁] 修复 2026 年 LangChain 0.3+ 移除 pydantic_v1 导致的所有旧版模型驱动崩溃
try:
    import langchain_core
    if "langchain_core.pydantic_v1" not in sys.modules:
        sys.modules["langchain_core.pydantic_v1"] = pydantic.v1
        logger.info("已在评测流程中成功建立 Pydantic v1 桥接层。")
except Exception as e:
    logger.warning(f"评测流补丁注入异常: {e}")

import json
import asyncio
from dotenv import load_dotenv
print("DEBUG: Importing DeepEval...")
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
print("DEBUG: Importing metrics...")
from tests.eval.metrics import (
    get_hsa_evidence_chain_metric, 
    HSANumericalPrecisionMetric,
    get_hsa_faithfulness_metric,
    get_hsa_answer_relevance_metric
)
print("DEBUG: Imports finished.")

# 强制切换到沙箱数据库环境
os.environ["CLICKHOUSE_DB"] = "hsa_sandbox"
load_dotenv(override=True)

import argparse

from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

async def run_evaluation(model_id: str = None):
    logger.info(f"正在启动医保稽核 Multi-Agent Graph 自动化评测流程 [模型: {model_id or '默认'}]...")
    
    # 1. 加载金标数据集
    dataset_path = "tests/eval/golden_dataset.json"
    if not os.path.exists(dataset_path):
        logger.error(f"找不到金标数据集: {dataset_path}")
        return None
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    # 2. 初始化 Graph 执行器
    executor, resolved_model_id = get_graph_executor(model_id=model_id)
    logger.info(f"物理图节点已并网: {resolved_model_id}")

    test_cases = []

    # 3. 运行 Graph 并收集结果
    for i, item in enumerate(golden_data):
        input_text = item["input"]
        logger.info(f"正在运行案例 {i+1}/{len(golden_data)}: {input_text}")
        
        try:
            # 执行 Graph
            # 注意：LangGraph 的输入是初始状态
            state = {
                "messages": [HumanMessage(content=input_text)],
                "model_id": resolved_model_id
            }
            # 使用同步调用简化评测循环（LangGraph invoke 是同步的，除非用了 Async 版本）
            response = executor.invoke(state)
            
            messages = response.get("messages", [])
            if not messages:
                logger.warning(f"案例 {i+1} 返回了空的消息列表")
                continue
                
            # 最终回复通常是最后一条消息
            actual_output = str(messages[-1].content)
            
            # 提取执行轨迹作为检索上下文 (Retrieval Context)
            # 我们记录所有的工具调用和返回，供 Faithfulness 指标评估真实性
            retrieval_context = []
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        retrieval_context.append(f"[Expert Task] Tool: {tc['name']} Args: {tc['args']}")
                elif isinstance(msg, ToolMessage):
                    retrieval_context.append(f"[Expert Evidence] Result: {msg.content}")
            
            # 构建 DeepEval 测试用例
            test_case = LLMTestCase(
                input=input_text,
                actual_output=actual_output,
                expected_output=item.get("expected_output"),
                context=[item.get("context")],
                retrieval_context=retrieval_context
            )
            test_cases.append(test_case)
        except Exception as e:
            logger.error(f"案例 {i+1} 运行并推导失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    if not test_cases:
        logger.warning("没有成功生成的测试用例，跳过打分。")
        return None

    # 4. 执行指标评测
    logger.info(f"Agent [{resolved_model_id}] 运行完成，开始进行指标打分...")
    
    evidence_chain_metric = get_hsa_evidence_chain_metric()
    precision_metric = HSANumericalPrecisionMetric()
    faithfulness_metric = get_hsa_faithfulness_metric()
    relevance_metric = get_hsa_answer_relevance_metric()

    # 使用 DeepEval 批量评估
    metrics = [evidence_chain_metric, precision_metric, faithfulness_metric, relevance_metric]
    import io
    from contextlib import redirect_stdout
    
    results = None
    f = io.StringIO()
    try:
        with redirect_stdout(f):
            results = evaluate(
                test_cases=test_cases,
                metrics=metrics
            )
    except Exception as e:
        logger.warning(f"指标打分过程发生异常 (已尝试规避渲染冲突): {e}")
        if not results:
            # 兜底：如果连评估逻辑都报错了，记录详细信息
            logger.error(f"DeepEval 评估内核报错: {e}")

    logger.success(f"模型 {resolved_model_id} 评测任务结束。")
    return {
        "model_id": resolved_model_id,
        "results": results,
        "test_cases_count": len(test_cases)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="医保稽核 Agent 自动化评测工具")
    parser.add_argument("--model", type=str, help="指定待测模型 ID (对应 llm_providers.json 中的 key)")
    args = parser.parse_args()
    
    asyncio.run(run_evaluation(model_id=args.model))
