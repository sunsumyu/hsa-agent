import asyncio
import json
from app.core.agent_graph import get_graph_executor, AuditState, AuditReport
from langchain_core.messages import HumanMessage
from tests.eval.metrics import NumericalPrecisionMetric
from deepeval.test_case import LLMTestCase

async def debug_case1():
    # Case 1 Input
    input_text = "请分析患者 PSN_20210001 在 2021 年 7 月至 10 月间的就医行为是否存在异常？"
    
    graph, _ = get_graph_executor()
    config = {"configurable": {"thread_id": "debug_case1"}}
    
    print("--- 正在执行 Case 1 ---")
    final_state = await graph.ainvoke({"messages": [HumanMessage(content=input_text)]}, config=config)
    
    report = final_state.get("structured_report")
    print(f"REPORT OBJECT: {report}")
    
    if report:
        print(f"TOTAL AMOUNT: {report.total_amount}")
        print(f"FINDINGS COUNT: {len(report.findings)}")
        for f in report.findings:
            print(f"  Finding Amount: {f.amount}")
            
        # 验证指标
        metric = NumericalPrecisionMetric()
        # Case 1 Ground Truth: [8398.92, 3201.0, 11599.92]
        expected = [8398.92, 3201.0, 11599.92]
        
        test_case = LLMTestCase(
            input=input_text,
            actual_output="...",
            additional_metadata={
                "structured_report": report.model_dump(),
                "ground_truth_amounts": expected
            }
        )
        
        score = metric.measure(test_case)
        print(f"CASE 1 SCORE: {score}")

if __name__ == "__main__":
    asyncio.run(debug_case1())
