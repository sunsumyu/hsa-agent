"""
scratch/verify_none_fix.py
==========================
验证 'NoneType' object has no attribute 'upper' 修复效果。
目标 Case: QA-06 (同时住院核查)
"""

import asyncio
import sys
import os

# 确保能找到 app 目录
sys.path.append(os.getcwd())

from app.core.agent_graph import workflow
from app.core.state import AuditState
from langchain_core.messages import HumanMessage
from loguru import logger

async def test_qa06():
    logger.info("🚀 开始验证 QA-06 (同时住院核查) 崩溃修复情况...")
    
    # 模拟 QA-06 的输入
    question = "核查是否存在同一患者在同一天内，在两家不同医院【同时住院】的情况？"
    
    # 初始化状态
    initial_state = {
        "messages": [HumanMessage(content=question)],
        "user_question": question,
        "retry_count": 0,
        "history": [],
        "sql_query": None,  # 显式设为 None，触发之前的崩溃点
        "metadata": {"tenant_id": "GLOBAL"}
    }
    
    # 配置
    config = {"configurable": {"thread_id": "verify-fix-01"}}
    
    try:
        logger.info("📡 正在调用 Agent Graph...")
        # workflow 已经由 app.core.agent_graph 编译完成
        app = workflow
        async for event in app.astream(initial_state, config):
            for node, state in event.items():
                logger.info(f"📍 Node: {node}")
                if state and "sql_query" in state:
                    logger.info(f"💎 SQL: {state['sql_query']}")
        
        logger.success("✅ 流程执行完成，未发生 NoneType 崩溃！")
        
    except Exception as e:
        logger.error(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_qa06())
