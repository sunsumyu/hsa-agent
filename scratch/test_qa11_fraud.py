import sys
import os
import asyncio
from loguru import logger

# 确保加载 app 模块
sys.path.append(os.getcwd())

from app.core.agent_graph import workflow
from app.infra.model_manager import model_manager

async def run_qa11_test():
    logger.info("🚀 [QA-11 专项测试] 启动：核查共用联系方式欺诈团伙")
    
    # 1. 任务描述
    question = "核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？"
    
    # 2. 初始化状态
    # 强行注入用户问题，并设置初始步骤
    initial_state = {
        "user_question": question,
        "history": [],
        "next_step": "auditor",
        "audit_results": [],
        "report": ""
    }
    
    logger.info(f"📝 任务: {question}")
    logger.info("--- [Agent 思考中] ---")
    
    # 3. 执行 Graph
    try:
        app = workflow
        # [V78.0] 为了观察工具调用，我们逐个节点流式打印
        async for event in app.astream(initial_state):
            for node_name, output in event.items():
                logger.info(f"📍 进入节点: {node_name}")
                if node_name == "auditor":
                    results = output.get("audit_results", [])
                    if results:
                        logger.success(f"✅ Auditor 节点已产生 {len(results)} 条初步发现")
                        for i, res in enumerate(results[:2]):
                            logger.info(f"   发现 {i+1}: {str(res)[:100]}...")
                
                if node_name == "reporter":
                    report = output.get("report", "")
                    print("\n" + "="*50)
                    print("📊 最终审计报告摘录:")
                    print("="*50)
                    print(report[:1500]) # 打印前1500字
                    print("="*50)
    
    except Exception as e:
        logger.error(f"❌ 测试运行崩溃: {e}")

if __name__ == "__main__":
    # 强行设置环境变量，避开坏掉的模型
    os.environ["PLANNER_MODEL_ID"] = "qwen-plus-bailian" # 强制使用高性能 Qwen
    
    asyncio.run(run_qa11_test())
