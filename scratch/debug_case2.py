import asyncio
import json
from app.core.agent_graph import AuditState, AuditReport, AuditFinding
from app.infra.model_manager import model_manager
from tests.eval.metrics import NumericalPrecisionMetric
from deepeval.test_case import LLMTestCase
from app.prompts import ANALYST_PROMPT

async def debug_case2():
    # 模拟 Case 2 的 Mock 数据 (来自工具返回)
    raw_data = json.dumps([
        {"institution_code": "H001", "total_medical_fee": 150000.50},
        {"institution_code": "H002", "total_medical_fee": 120000.75},
        {"institution_code": "H003", "total_medical_fee": 90000.00}
    ])
    
    # 获取 Analyst 
    analyst_llm, _ = model_manager.get_llm_by_role("reporter")
    structured_analyst = analyst_llm.with_structured_output(AuditReport)
    
    a_prompt = ANALYST_PROMPT.format_messages(
        messages=[],
        raw_data=raw_data
    )
    
    print("--- 正在调用 Analyst 提取结构化数据 ---")
    report = await structured_analyst.ainvoke(a_prompt)
    
    print(f"REPORT SUMMARY: {report.summary}")
    print(f"FINDINGS COUNT: {len(report.findings)}")
    for f in report.findings:
        print(f"FOUND AMOUNT: {f.amount}")
    print(f"TOTAL AMOUNT: {report.total_amount}")

    # 验证指标对照
    metric = NumericalPrecisionMetric()
    expected_nums = [150000.50, 120000.75, 90000.00] # 假设这是 Case 2 的 Ground Truth
    
    test_case = LLMTestCase(
        input="...",
        actual_output="...",
        additional_metadata={
            "structured_report": report.model_dump(),
            "ground_truth_amounts": expected_nums
        }
    )
    
    score = metric.measure(test_case)
    print(f"FINAL DEBUG SCORE: {score}")

if __name__ == "__main__":
    asyncio.run(debug_case2())
