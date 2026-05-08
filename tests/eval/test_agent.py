import os
import json
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from tests.eval.metrics import get_hsa_evidence_chain_metric, NumericalPrecisionMetric as HSANumericalPrecisionMetric
from dotenv import load_dotenv

# 确保在运行前正确加载环境
os.environ["CLICKHOUSE_DB"] = "hsa_sandbox"
load_dotenv(override=True)

from app.agent_graph import get_graph_executor as get_executor

def get_golden_data():
    dataset_path = "tests/eval/golden_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.mark.asyncio
@pytest.mark.parametrize("item", get_golden_data())
async def test_medical_agent(item):
    """医保稽核 Agent 自动化回归测试项。"""
    app, _ = get_executor()
    
    # 1. 运行 Agent (适配 LangGraph V36.9 格式)
    input_text = item["input"]
    inputs = {
        "messages": [("user", input_text)],
        "session_id": "test_regression",
        "retry_count": 0
    }
    config = {"configurable": {"thread_id": "test_thread"}}
    
    state = await app.ainvoke(inputs, config=config)
    
    # 从状态中提取最终回答 (Markdown 报表)
    final_output = state["messages"][-1].content if state["messages"] else ""
    
    # 2. 构建指标项
    evidence_chain_metric = get_hsa_evidence_chain_metric()
    precision_metric = HSANumericalPrecisionMetric()
    
    # 3. 创建测试用例
    test_case = LLMTestCase(
        input=input_text,
        actual_output=final_output,
        expected_output=item.get("expected_output"),
        context=[item.get("context")]
    )
    
    # 4. 断言检查
    assert_test(test_case, [evidence_chain_metric, precision_metric])
