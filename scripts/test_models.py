import asyncio
import os
from loguru import logger
from app.model_manager import model_manager

async def test_all_providers():
    roles = ["planner", "coder", "reporter"]
    for role in roles:
        print(f"\n--- Testing Role: {role} ---")
        try:
            llm, model_name = model_manager.get_llm_by_role(role)
            print(f"Selected Primary: {model_name}")
            
            # 尝试发送一个极简请求
            from langchain_core.messages import HumanMessage
            resp = await llm.ainvoke([HumanMessage(content="Hi")])
            print(f"Response from {model_name}: {resp.content[:50]}...")
            
        except Exception as e:
            print(f"Error testing {role}: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_providers())
