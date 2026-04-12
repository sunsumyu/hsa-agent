import asyncio
import os
import sys
import traceback
from loguru import logger

# Setup Project Root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage
from app.tools import execute_audit_sql

async def debug_probe():
    logger.info("--- 正在启动深度诊断探测器 (Gemma版) ---")
    
    # 1. 检查数据库连接 (沙箱环境)
    os.environ["CLICKHOUSE_DB"] = "hsa_sandbox"
    try:
        count = execute_audit_sql.invoke("SELECT count() FROM fqz_gz_jzsj_all_ql")
        logger.success(f"数据库连接正常，沙箱数据量: {count}")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return

    # 2. 检查模型加载 (Gemma 4 31B via DeepInfra)
    model_id = "gemma-4-31b-it"
    try:
        executor, resolved_id = get_graph_executor(model_id=model_id)
        logger.success(f"模型并网成功: {resolved_id}")
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        logger.error(traceback.format_exc())
        return

    # 3. 运行单案例抓取完整输出
    test_input = "查询参保人 P99999 在 2026年1月的就诊记录，并核对总金额是否为 1450.90 元。"
    logger.info(f"正在测试案例: {test_input}")
    
    try:
        state = {
            "messages": [HumanMessage(content=test_input)],
            "model_id": model_id
        }
        response = executor.invoke(state)
        
        logger.info("--- 完整消息流回顾 ---")
        for msg in response["messages"]:
            if hasattr(msg, "content"):
                role = "AI" if not hasattr(msg, "tool_calls") else "Expert"
                logger.info(f"[{role}]: {msg.content[:200]}...")
            else:
                logger.info(f"[ToolResult]: {str(msg)[:200]}...")
            
        logger.success("探测器运行完成，DeepInfra 链路健康。")
    except Exception as e:
        logger.error(f"运行阶段崩溃: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(debug_probe())
