import asyncio
import os
import sys
from loguru import logger

# Add project root to PYTHONPATH
sys.path.append(os.getcwd())

from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from langchain_core.messages import HumanMessage

async def probe_model(model_id: str):
    print(f"\n[PROBE] Testing model_id: {model_id}")
    try:
        cfg = model_manager.providers.get(model_id)
        if not cfg:
            print(f"  Result: Model ID not found in config")
            return
            
        llm = model_manager._create_llm(model_id, cfg, bypass_limit=True)
        if not llm:
            print(f"  Result: Failed to create LLM (missing API Key?)")
            return
            
        resp = await llm.ainvoke([HumanMessage(content="1+1=?")])
        print(f"  Result: SUCCESS | Response: {resp.content}")
        usage_tracker.record_success(model_id)
    except Exception as e:
        print(f"  Result: FAILED | Error: {e}")
        usage_tracker.record_failure(model_id, str(e))

async def main():
    models_to_test = ["deepseek-v3", "qwen2.5-32b-instruct", "qwen-long"]
    for m in models_to_test:
        await probe_model(m)

if __name__ == "__main__":
    asyncio.run(main())
