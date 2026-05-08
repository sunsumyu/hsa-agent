import os
import json
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, messages_from_dict, messages_to_dict
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

    def get_latest_session_id(self) -> str:
        """获取最近活跃的会话 ID"""
        if not os.path.exists(self.storage_dir):
            return "default-python-session"
            
        files = [f for f in os.listdir(self.storage_dir) if f.endswith(".json") and f != "default-python-session.json"]
        if not files:
            return "default-python-session"
            
        # 按修改时间排序
        files.sort(key=lambda x: os.path.getmtime(os.path.join(self.storage_dir, x)), reverse=True)
        return files[0].replace(".json", "")

    def get_history(self, session_id: str, auto_recover: bool = False) -> List[BaseMessage]:
        """获取指定会话的历史记录"""
        path = self._get_path(session_id)
        
        # 如果当前 session 为空且开启了自动恢复
        if not os.path.exists(path) and auto_recover:
            latest_id = self.get_latest_session_id()
            if latest_id != session_id:
                logger.info(f"正在自动恢复最近会话: {latest_id}")
                path = self._get_path(latest_id)

        if not os.path.exists(path):
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
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

    def dump_debug_history(self, session_id: str, messages: List[BaseMessage], internal_steps: List[str] = None):
        """[V18.1] 深度转储：包含影子思维链的全量审计记录"""
        debug_dir = os.path.join("data", "debug")
        os.makedirs(debug_dir, exist_ok=True)
        
        safe_id = "".join([c for c in session_id if c.isalnum() or c in "-_"])
        filename = f"{safe_id}_full_dump.txt"
        path = os.path.join(debug_dir, filename)
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"=== HSA Session Deep Debug Dump ===\n")
                f.write(f"Session ID: {session_id}\n")
                f.write(f"Message Count: {len(messages)}\n")
                if internal_steps:
                    f.write(f"Internal Steps (Thoughts): {len(internal_steps)}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"=============================\n\n")
                
                if internal_steps:
                    f.write(f"--- 🧩 INTERNAL STEPS (Shadow Reasoning) ---\n")
                    for i, step in enumerate(internal_steps):
                        f.write(f"[{i:02d}] {step}\n")
                    f.write(f"-------------------------------------------\n\n")

                for i, msg in enumerate(messages):
                    f.write(f"--- [{i:05d}] {msg.__class__.__name__} ---\n")
                    f.write(f"Content: {msg.content}\n")
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        f.write(f"Tool Calls: {json.dumps(msg.tool_calls, ensure_ascii=False)}\n")
                    if isinstance(msg, ToolMessage):
                        f.write(f"Tool Call ID: {msg.tool_call_id}\n")
                    f.write("\n")
            logger.warning(f">>> [调试转储] 已生成会话历史镜像: {path}")
        except Exception as e:
            logger.error(f"生成调试转储失败: {e}")

# 全局单例
history_manager = HistoryManager()
from datetime import datetime
