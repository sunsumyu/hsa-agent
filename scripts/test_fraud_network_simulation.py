import os
import sys
import asyncio
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
os.environ["HF_HOME"] = "E:\\hf_cache"

from app.agent_graph import workflow

async def run_fraud_network_sim():
    logger.info("🕸️ [SCENARIO] 正在开启：欺诈网络团伙分析模拟...")
    
    user_input = (
        "分析近期结算数据，重点识别是否存在多个患者共用同一地址或由同一医生密集开药的异常团伙特征。"
    )
    
    inputs = {
        "messages": [("user", user_input)],
        "session_id": "fraud_network_session_99",
        "loop_count": 0
    }
    config = {"configurable": {"thread_id": "fraud_sim_01"}}

    logger.info(f">>> 审计指令: {user_input}")

    async for output in workflow.astream(inputs, config=config):
        for node_name, state in output.items():
            if node_name == "REPORTER":
                report = state.get("structured_report")
                if report:
                    logger.success("🏆 [SIMULATION] 团伙欺诈分析报告已生成！")
                    logger.info(f"违规类型: {[f.violation_type for f in report.findings]}")
                    logger.info(f"动态风险评分: {report.risk_scores}")
                    
                    # 验证关键维度
                    if report.risk_scores.get("发现隐蔽性", 0) > 50:
                        logger.success("🎯 [SUCCESS] 智能体成功识别出‘欺诈隐蔽性’特征并进行了加权评分。")
                    if report.risk_scores.get("再犯风险", 0) > 30:
                        logger.success("🎯 [SUCCESS] 智能体成功评估了团伙化的‘再犯风险’。")

                print(state["messages"][-1].content)

if __name__ == "__main__":
    asyncio.run(run_fraud_network_sim())
