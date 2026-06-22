import asyncio
from app.core.llm_provider import llm_provider
from app.core.registry import skill_registry
from app.core.permission_manager import permission_manager
from langchain_core.messages import HumanMessage, SystemMessage

async def main():
    all_tools = skill_registry.get_all_skills()
    tools = permission_manager.filter_skills("default_admin", all_tools)
    
    state = {
        "messages": [
            SystemMessage(content="你是一名精通医疗稽核的数据专家。你的核心任务是根据方法论编写精准的取证代码。"),
            HumanMessage(content="查询理疗科手法治疗的项目清单。请调用 lookup_medical_schema 工具。")
        ],
        "target_tables": [],
        "session_id": "test_session",
        "retry_count": 0,
        "metadata": {
            "user_question": "查询理疗科手法治疗的项目清单。"
        }
    }
    
    res = await llm_provider.chat(
        role="coder",
        messages=state["messages"],
        state=state,
        tools=tools
    )
    
    print(f"Response Type: {type(res)}")
    print(f"Response Content: {res.content[:200]}")
    print(f"Response Tool Calls: {getattr(res, 'tool_calls', None)}")

if __name__ == "__main__":
    asyncio.run(main())
