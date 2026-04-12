import asyncio
from app.agent_graph import audit_app
from langchain_core.messages import HumanMessage
import os

async def main():
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    # Run one step
    print("--- 启动第一轮对话 ---")
    inputs = {"messages": [HumanMessage(content="你好，请检查库表。")], "model_id": "qwen-max"}
    async for event in audit_app.astream_events(inputs, config, version="v1"):
        if event["event"] == "on_chain_start" and event["name"] == "supervisor":
            print(f"进入节点: {event['name']}")

    # Check state
    state = audit_app.get_state(config)
    print(f"当前节点: {state.next}")
    print(f"消息数量: {len(state.values['messages'])}")

    # Try to resume or just check DB file
    if os.path.exists("audit_checkpoints.db"):
        print("SUCCESS: audit_checkpoints.db 已创建。")
    else:
        print("FAILED: audit_checkpoints.db 未找到。")

if __name__ == "__main__":
    asyncio.run(main())
