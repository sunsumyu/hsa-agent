import asyncio
import os
import sys
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 将项目根目录添加到路径
sys.path.append(r"e:\chain\hsa-agent")

from app.core.context import tenant_context
from app.tools import manage_memory

async def test_compliance():
    print("🔍 模拟 Agent 进行合规性检索...")
    
    # 设置租户上下文为 SYSTEM_GLOBAL (或不设置，因为它会自动回溯)
    tenant_context.set("SYSTEM_GLOBAL")
    
    query = "对于分解项目收费，条例规定如何处罚？"
    
    print(f"User Question: {query}")
    
    # 模拟 Agent 调用管理工具搜索记忆
    search_res = await manage_memory.ainvoke({
        "action": "search",
        "query": query,
        "limit": 3
    })
    
    print(f"\n--- [Memory Recall Results] ---\n{search_res}")
    
    # 验证是否召回了相关的第35条
    if "第三十五条" in search_res:
        print("\n✅ 成功召回相关的监管条款（第三十五条）。")
    else:
        print("\n❌ 未能找到相关的监管条款。")

if __name__ == "__main__":
    asyncio.run(test_compliance())
