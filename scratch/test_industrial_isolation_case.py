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

async def run_isolation_test():
    print("🏥 [医疗工业测试] 开始执行高隔离记忆检索验证...")

    # --- 步骤 1: 上海中心医院存入私有审计经验 ---
    tenant_context.set("CITY_SH_001")
    print("\n[租户: 上海中心医院] 正在存入私有审计经验...")
    await manage_memory.ainvoke({
        "action": "add",
        "content": "【私有经验】针对日间手术虚构住院，重点核查病历中的‘入院体温’是否连续 3 天完全一致，这通常是批量伪造病历的特征。",
        "memory_type": "semantic",
        "importance": 0.9
    })
    print("✅ 上海租户经验已存入物理隔离层。")

    # --- 步骤 2: 北京协和分院尝试检索（模拟信息泄露风险点） ---
    tenant_context.set("CITY_BJ_002")
    print("\n[租户: 北京市协和分院] 正在搜索：'虚假住院审计技巧'...")
    bj_res = await manage_memory.ainvoke({
        "action": "search",
        "query": "虚假住院审计技巧",
        "limit": 5
    })
    
    leak_detected = "入院体温" in bj_res
    if not leak_detected:
        print("🛡️ [安全验证通过] 北京租户未搜索到上海租户的私有信息。")
    else:
        print("⚠️ [安全预警] 检测到跨租户数据泄露！")

    # --- 步骤 3: 上海中心医院正常检索 ---
    tenant_context.set("CITY_SH_001")
    print("\n[租户: 上海中心医院] 正在搜索：'虚假住院审计技巧'...")
    sh_res = await manage_memory.ainvoke({
        "action": "search",
        "query": "虚假住院审计技巧",
        "limit": 5
    })
    
    if "入院体温" in sh_res:
        print("🎯 [精准召回成功] 上海租户成功找回了本租户的私有审计经验。")
    else:
        print("❌ [召回失败] 未能找到预期的记忆。")

    print("\n--- 验证总结 ---")
    print(f"数据隔离性: {'符合工业级标准' if not leak_detected else '不符合'}")
    print(f"业务精准度: {'符合工业级标准' if '入院体温' in sh_res else '不符合'}")

if __name__ == "__main__":
    asyncio.run(run_isolation_test())
