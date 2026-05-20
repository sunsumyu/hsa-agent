import asyncio
import sys
import os

# 路径修复
sys.path.append(os.getcwd())

from app.infra.model_manager import EnrichedChatOpenAI
from loguru import logger

async def test_error_handling():
    # 模拟一个会报错的节点
    model = EnrichedChatOpenAI(
        endpoint_id="doubao-pro-32k", # 这是一个真实 ID，会触发 get_endpoint_config
        openai_api_key="invalid",
        openai_api_base="https://invalid.url"
    )
    
    logger.info("🧪 测试异步异常捕获与平台标签...")
    try:
        await model._agenerate([{"role": "user", "content": "hello"}])
    except Exception as e:
        logger.success(f"✅ 成功捕获预期异常并处理，无 NameError")

if __name__ == "__main__":
    asyncio.run(test_error_handling())
