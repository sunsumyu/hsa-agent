import asyncio
import json
from app.core.agent_graph import AuditState, AuditReport, AuditFinding
from app.infra.model_manager import model_manager
from tests.eval.metrics import NumericalPrecisionMetric
from deepeval.test_case import LLMTestCase
from loguru import logger

async def debug_l2():
    metric = NumericalPrecisionMetric()
    
    # Simulate a successful SQL result
    raw_data = json.dumps([
        {"medfee_sumamt": 8398.92, "visit_date": "2021-07-10"},
        {"medfee_sumamt": 3201.00, "visit_date": "2021-08-15"}
    ])
    
    # Mock a finding
    findings = [
        AuditFinding(violation_type="异常", evidence="证据", amount=8398.92, count=1, policy_basis="X"),
        AuditFinding(violation_type="异常", evidence="证据", amount=3201.00, count=1, policy_basis="X")
    ]
    report = AuditReport(summary="总结", findings=findings, total_amount=11599.92, risk_level="高")
    
    # Test case with ground truth from Case 1
    test_case = LLMTestCase(
        input="...",
        actual_output="...",
        additional_metadata={
            "structured_report": report,
            "ground_truth_amounts": [8398.92, 3201.00, 11599.92]
        }
    )
    
    score = metric.measure(test_case)
    print(f"DEBUG SCORE: {score}")
    print(f"ACTUAL NUMS: {metric._extract_from_structured(test_case.additional_metadata)}")

if __name__ == "__main__":
    asyncio.run(debug_l2())
