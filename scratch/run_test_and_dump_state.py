import asyncio
import os
import sys
import io

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.core.agent_graph import build_graph

async def main():
    question = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
    workflow = build_graph()
    
    print("[RUN] Question:", question)
    state = await workflow.ainvoke(
        {"messages": [("user", question)], "session_id": "test-dump-state"},
        config={"recursion_limit": 30}
    )
    
    print("=" * 80)
    print("State keys:", list(state.keys()))
    for k, v in state.items():
        if k == "messages":
            print(f"messages: {len(v)} messages")
            for idx, m in enumerate(v):
                print(f"  {idx}: {m.__class__.__name__}(content={str(m.content)[:100]!r}, tool_calls={getattr(m, 'tool_calls', None)})")
        elif k == "raw_data":
            print(f"raw_data: {v!r}")
        elif k == "sql_query":
            print(f"sql_query: {v!r}")
        elif k == "sql_history":
            print(f"sql_history: {v!r}")
        elif k == "structured_report":
            if v:
                print(f"structured_report model_dump: {v.model_dump() if hasattr(v, 'model_dump') else v}")
            else:
                print("structured_report: None")
        else:
            print(f"{k}: {v!r}")

if __name__ == "__main__":
    asyncio.run(main())
