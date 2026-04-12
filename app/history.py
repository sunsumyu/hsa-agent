import os
import json
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, messages_from_dict, messages_to_dict
from loguru import logger

class HistoryManager:
    """
    基于本地 JSON 文件的会话历史管理器。
    存储路径: data/history/[session_id].json
    """
    def __init__(self, storage_dir: str = "data/history", max_messages: int = 20):
        self.storage_dir = storage_dir
        self.max_messages = max_messages
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, session_id: str) -> str:
        # 清理文件名防止注入
        safe_id = "".join([c for c in session_id if c.isalnum() or c in "-_"])
        return os.path.join(self.storage_dir, f"{safe_id}.json")

    def get_history(self, session_id: str) -> List[BaseMessage]:
        """获取指定会话的历史记录"""
        path = self._get_path(session_id)
        if not os.path.exists(path):
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 使用 LangChain 内置工具恢复消息对象
                return messages_from_dict(data)
        except Exception as e:
            logger.error(f"读取历史记录失败 [Session: {session_id}]: {e}")
            return []

    def save_turn(self, session_id: str, human_msg: str, ai_msg: str):
        """保存一轮对话"""
        history = self.get_history(session_id)
        
        # 添加新消息
        history.append(HumanMessage(content=human_msg))
        history.append(AIMessage(content=ai_msg))
        
        # 截断历史记录，保持在 max_messages 以内
        if len(history) > self.max_messages:
            history = history[-self.max_messages:]
            
        path = self._get_path(session_id)
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                # 转换回字典列表进行存储
                json.dump(messages_to_dict(history), f, ensure_ascii=False, indent=2)
            logger.info(f"已更新会话历史 [Session: {session_id}]")
        except Exception as e:
            logger.error(f"保存历史记录失败 [Session: {session_id}]: {e}")

# 全局单例
history_manager = HistoryManager()
