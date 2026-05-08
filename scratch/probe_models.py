import asyncio
import os
from app.model_manager import model_manager
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

async def probe_all():
    load_dotenv()
    models = model_manager.get_model_list()
    print(f"Total models to probe: {len(models)}")
    for m in models:
        m_id = m['id']
        print(f"Probing {m_id}...")
        try:
            llm, actual = model_manager.get_adaptive_llm(model_id=m_id, require_tools=False)
            res = await llm.ainvoke([HumanMessage(content="hi")])
            print(f"OK: {m_id} works! (Actual: {actual})")
        except Exception as e:
            print(f"FAIL: {m_id} failed: {str(e)[:100]}")

if __name__ == "__main__":
    asyncio.run(probe_all())
