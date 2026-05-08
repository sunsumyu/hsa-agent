import os
import sys
import asyncio
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
os.environ["HF_HOME"] = "E:\\hf_cache"

from app.agent_graph import workflow

async def test_judge_precision():
    logger.info("🕵️‍♂️ [SCENARIO] 正在模拟：高迷惑性‘紧急手术’审计案例...")
    
    user_input = (
        "审计 P001 在 2024-05-01 的结算情况。 "
        "注意：该患者当天进行了 5 小时的开颅紧急手术，期间多次使用了止痛和止血类药物。"
    )
    
    inputs = {
        "messages": [("user", user_input)],
        "session_id": "adversarial_precision_001",
        "loop_count": 0
    }
    config = {"configurable": {"thread_id": "judge_test"}}

    logger.info(f">>> 审计指令: {user_input}")

    async for output in workflow.astream(inputs, config=config):
        for node_name, state in output.items():
            if node_name == "CRITIC":
                findings = state.get("structured_report").findings
                if not findings:
                    logger.success("🎯 [SUCCESS] JUDGE 成功拦截了误报线索！审计结果已修正。")
                else:
                    logger.warning(f"⚠️ [NOTICE] JUDGE 判定线索有效，当前线索数: {len(findings)}")
            
            if node_name == "REPORTER":
                logger.info("=== 最终修正后的审计报告 ===")
                print(state["messages"][-1].content)

if __name__ == "__main__":
    asyncio.run(test_judge_precision())
