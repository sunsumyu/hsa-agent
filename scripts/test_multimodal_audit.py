import os
import sys
import json
import asyncio
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
os.environ["HF_HOME"] = "E:\\hf_cache"

from app.agent_graph import workflow

async def test_multimodal_penetration():
    logger.info("=== [Phase 1: 多模态输入] ===")
    image_path = "handwritten_prescription_audit_demo_1777647786433.png"
    user_input = (
        f"附件是一张患者张*的处方单 (路径: {image_path})。 "
        "请帮我对比 ClickHouse 结算数据中该患者在 2024-05-01 的实际开药记录，"
        "看看是否存在【虚增药品】的行为。"
    )
    
    logger.info(f">>> 审计指令: {user_input}")

    # 运行 Agent Graph
    config = {"configurable": {"thread_id": "multimodal_test_001"}}
    inputs = {"messages": [("user", user_input)]}
    
    async for output in workflow.astream(inputs, config=config):
        for node_name, state in output.items():
            logger.info(f"--- 节点执行完毕: {node_name} ---")
            if node_name == "REPORTER":
                content = state["messages"][-1].content
                logger.success("=== [最终穿透审计报告] ===")
                print(content)

if __name__ == "__main__":
    asyncio.run(test_multimodal_penetration())
