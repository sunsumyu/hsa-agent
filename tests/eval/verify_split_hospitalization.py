import asyncio
from app.agents.agent import get_executor
from loguru import logger

async def verify():
    logger.info("Verifying 'Split Hospitalization' with enriched Knowledge Base...")
    executor, resolved_id = get_executor(model_id="gemma-4-31b-it")
    
    query = "分析患者 P99999 在 15 天内是否有‘分解住院’风险？请给出具体的第二次入院日期和间隔天数。"
    
    logger.info(f"Query: {query}")
    response = await executor.ainvoke({"input": query, "chat_history": []})
    
    print("\n--- AGENT RESPONSE ---")
    print(response["output"])
    print("----------------------\n")

if __name__ == "__main__":
    asyncio.run(verify())
