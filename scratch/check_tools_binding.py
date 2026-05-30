import asyncio
from app.infra.model_manager import model_manager
from app.core.registry import skill_registry
from app.core.permission_manager import permission_manager
from langchain_core.messages import HumanMessage

async def main():
    llm, m_id = await model_manager.get_llm_by_role("coder")
    print(f"Model ID: {m_id}")
    print(f"LLM Type: {type(llm)}")
    
    all_tools = skill_registry.get_all_skills()
    tools = permission_manager.filter_skills("default_admin", all_tools)
    print(f"Total tools: {len(tools)}")
    
    # Try binding tools
    try:
        bound_llm = llm.bind_tools(tools)
        print("Successfully called bind_tools on LLM object!")
        
        # Test invocation
        res = await bound_llm.ainvoke([HumanMessage(content="查询理疗科手法治疗的项目清单。请调用 lookup_medical_schema 工具。")])
        print(f"Response Type: {type(res)}")
        print(f"Response Content: {res.content[:200]}")
        print(f"Response Tool Calls: {getattr(res, 'tool_calls', None)}")
    except Exception as e:
        print(f"Failed to bind or invoke: {e}")

if __name__ == "__main__":
    asyncio.run(main())
