import asyncio
from app.core.agent_graph import workflow as audit_graph

async def main():
    # 构造复杂泛化性问题
    question = "核查 2024 年所有跨市异地就医（参保地与机构地不同）且报销比例异常（大于 90% 或小于 10%）的案例，展示前 10 条高额记录，并说明审计方法论。"
    
    print(f"[Generalization Test] Starting new audit task...")
    print(f"Question: {question}\n")
    
    initial_state = {
        "messages": [],
        "tasks": [question],
        "session_id": "test_gen_v119",
        "metadata": {
            "user_question": question
        }
    }
    
    async for event in audit_graph.astream(initial_state):
        for node_name, state in event.items():
            print(f"\n[Node] {node_name}")
            if node_name == "auditor_node":
                if state.get("sql_query"):
                    print(f"Generated SQL:\n{state['sql_query']}")
                if state.get("error_log"):
                    print(f"Error: {state['error_log']}")
            elif node_name == "reporter_node":
                print(f"Final Report Generated. Checking dashboard_latest.html...")

if __name__ == "__main__":
    asyncio.run(main())
