import json
import os
import sys
import io
import asyncio
from langchain_core.messages import HumanMessage
from app.core.agent_graph import get_graph_executor

# Setup UTF-8 Output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main():
    dataset_path = r"e:\chain\hsa-agent\tests\eval\golden_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    executor, resolved_id = get_graph_executor(model_id="gemma-4-31b-it")
    print(f"--- Starting Mini-Eval (Model: {resolved_id}) ---\n")

    for i, item in enumerate(golden_data):
        input_text = item["input"]
        print(f"CASE {i+1} INPUT: {input_text}")
        
        try:
            state = {
                "messages": [HumanMessage(content=input_text)],
                "model_id": resolved_id
            }
            # LangGraph invoke is synchronous
            response = executor.invoke(state)
            actual_output = response["messages"][-1].content
            
            print(f"CASE {i+1} OUTPUT:\n{actual_output}")
            print(f"CASE {i+1} EXPECTED:\n{item['expected_output']}")
            print("-" * 50)
        except Exception as e:
            print(f"CASE {i+1} ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())

