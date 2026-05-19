import os
import json
import asyncio
from typing import List
from app.memory.history import history_manager
from app.memory.semantic_memory import semantic_memory_manager
from loguru import logger

async def batch_index_session(session_id: str):
    """[V5.1.0] 批量索引脚本：为历史存量消息补录语义索引"""
    logger.info(f">>> [批量索引] 正在加载会话历史: {session_id}")
    
    # 获取所有存储的 BaseMessage 对象
    messages = history_manager.get_history(session_id)
    if not messages:
        logger.warning(f"会话 {session_id} 无历史消息，跳过。")
        return
        
    logger.info(f"检测到 {len(messages)} 条历史消息，正在进行向量化...")
    
    # 批量处理
    await semantic_memory_manager.archive_messages(session_id, messages)
    
    logger.info(f"✅ [批量索引完成] 会话 {session_id} 的全量语义库已建立。")

if __name__ == "__main__":
    # 默认处理最近活跃的会话
    latest_id = history_manager.get_latest_session_id()
    if latest_id:
        asyncio.run(batch_index_session(latest_id))
    else:
        logger.error("未找到有效的会话历史文件。")
