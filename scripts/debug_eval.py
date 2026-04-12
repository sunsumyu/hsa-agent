import os
import sys
from loguru import logger

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.evaluate_agent import run_evaluation
import asyncio

async def test():
    res = await run_evaluation(model_id="qwen-max")
    eval_result = res['results']
    print(f"EVALUATION RESULT TYPE: {type(eval_result)}")
    if hasattr(eval_result, 'test_results') and len(eval_result.test_results) > 0:
        first_test = eval_result.test_results[0]
        print(f"FIRST TEST RESULT TYPE: {type(first_test)}")
        print(f"FIRST TEST RESULT DIR: {dir(first_test)}")
        if hasattr(first_test, 'metrics') or hasattr(first_test, 'metrics_results'):
            print("Found metrics/metrics_results attribute")

if __name__ == "__main__":
    asyncio.run(test())
