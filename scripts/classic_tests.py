import asyncio
import os
import sys
from loguru import logger

# 确保项目路径正确
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.agent import get_executor

async def run_classic_test(question: str, session_id: str):
    logger.info(f"\n🚀 [测试开始] 问题: {question}")
    executor, _ = get_executor()
    
    inputs = {
        "input": question,
        "chat_history": [],
        "session_id": session_id
    }
    
    try:
        # 使用 ainvoke 执行 AgentGraph
        result = await executor.ainvoke(inputs)
        
        print("\n" + "='*50")
        print(f"🤖 Agent 最终回复 (Session: {session_id}):")
        print(result["output"])
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"测试执行失败: {e}")

async def main():
    # 5 个医保审计经典问题测试集
    tests = [
        "查询 2024 年是否存在同一患者在同一天结算两次住院费用的情况，列出嫌疑机构。",
        "分析是否存在将‘全自动生化分析’拆分为多个单项重复收费的嫌疑，请调取相关政策依据。",
        "查找住院天数超过 90 天且每日平均费用低于 50 元的病例，识别‘挂床住院’风险。",
        "检索是否存在单张处方中药品品种超过 10 种或总金额超过 5000 元的异常记录。",
        "根据医保政策，对于‘日间手术’的结算比例和准入条件是什么？并对比当前库中的结算数据。"
    ]

    for i, q in enumerate(tests):
        session_id = f"classic_test_{i+1}"
        await run_classic_test(q, session_id)
        # 稍微停顿，模拟真实交互
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
