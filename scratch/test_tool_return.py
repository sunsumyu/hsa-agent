import os
import sys
sys.path.append(os.getcwd())
import asyncio
from app.core.registry import skill_registry

async def test_tool():
    tool = skill_registry.get_skill("execute_audit_sql")
    print(f"Tool class: {tool.__class__.__name__}")
    
    # Try running the tool
    args = {"sql": "SELECT 1", "state": {"metadata": {}}}
    res = await tool.ainvoke(args)
    print(f"Result type: {type(res)}")
    print(f"Result value: {repr(res)}")

if __name__ == "__main__":
    asyncio.run(test_tool())
