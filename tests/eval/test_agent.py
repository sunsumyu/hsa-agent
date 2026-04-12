import os
import json
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from tests.eval.metrics import get_hsa_evidence_chain_metric, HSANumericalPrecisionMetric
from dotenv import load_dotenv

# 确保在运行前正确加载环境
os.environ["CLICKHOUSE_DB"] = "hsa_sandbox"
load_dotenv(override=True)

from app.agent import get_executor

def get_golden_data():
    dataset_path = "tests/eval/golden_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.mark.parametrize("item", get_golden_data())
def test_medical_agent(item):
    """医保稽核 Agent 自动化回归测试项。"""
    executor, _ = get_executor()
    
    # 1. 运行 Agent
    input_text = item["input"]
    response = executor.invoke({"input": input_text, "chat_history": []})
    actual_output = response["output"]
    
    # 2. 构建指标项
    evidence_chain_metric = get_hsa_evidence_chain_metric()
    precision_metric = HSANumericalPrecisionMetric()
    
    # 3. 创建测试用例
    test_case = LLMTestCase(
        input=input_text,
        actual_output=actual_output,
        expected_output=item.get("expected_output"),
        context=[item.get("context")]
    )
    
    # 4. 断言检查（不通过时抛出异常并详细报告）
    assert_test(test_case, [evidence_chain_metric, precision_metric])
