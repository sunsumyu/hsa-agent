#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试 QA-CUST-27 的核心问题：语义偏离
不依赖完整流，只测试关键的部分
"""
import asyncio
from langchain_core.messages import HumanMessage
from app.core.agent_graph import get_graph_executor

async def test_qa_cust27():
    """测试 QA-CUST-27 是否仍存在语义偏离"""

    question = "查最近5年单次结算金额排名最高的异常案件，把大额的都找出来，看看哪些医院和患者频繁出现大额结算，按金额从高到低列出来。"

    print("=" * 60)
    print(f"测试问题: {question}")
    print("=" * 60)

    executor, model_id = get_graph_executor(model_id="qwen-max")

    config = {
        "configurable": {"thread_id": f"test_{int(asyncio.get_event_loop().time())}"},
        "recursion_limit": 80
    }

    state = {
        "messages": [HumanMessage(content=question)],
        "model_id": model_id
    }

    start_time = asyncio.get_event_loop().time()

    try:
        response = await executor.ainvoke(state, config=config)

        # 提取关键信息
        last_msg = response["messages"][-1].content

        print("\n" + "=" * 60)
        print("Agent 输出 (前 500 字):")
        print("=" * 60)
        print(last_msg[:500])

        # 检查 SQL 是否有 GROUP BY 金额的问题
        print("\n" + "=" * 60)
        print("SQL 分析:")
        print("=" * 60)

        if "GROUP BY medfee_sumamt" in last_msg:
            print("❌ 问题：发现 GROUP BY medfee_sumamt（按金额分组）")
            print("   正确应该是：ORDER BY medfee_sumamt DESC LIMIT 100")
        elif "ORDER BY medfee_sumamt" in last_msg:
            print("✅ 正确：包含 ORDER BY medfee_sumamt")
        else:
            print("⚠️  未能明确验证 SQL 结构")

        # 统计平均行数
        if "共发现" in last_msg or "共 100" in last_msg:
            print("✅ 输出符合预期（金额从高到低排名）")
        elif "频次" in last_msg and "GROUP BY" in last_msg:
            print("❌ 问题：描述了频次而不是金额排名")
        else:
            print("⚠️  输出结构需要进一步分析")

        elapsed = asyncio.get_event_loop().time() - start_time
        print(f"\n═══ 耗时: {elapsed:.1f}s ═══")

    except Exception as e:
        print(f"❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_qa_cust27())
