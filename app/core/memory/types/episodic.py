"""
app/core/memory/types/episodic.py
=================================
[V178.5] 情景记忆层 (Episodic Memory Type) - 审计经验专家
"""

from typing import List, Any, Optional, Dict
from loguru import logger
from datetime import datetime
from app.core.memory.base import MemoryItem
from app.core.memory.storage.relational import RelationalStorage

class EpisodicMemory:
    """
    情景记忆：负责记录和召回过去的审计动作链、决策逻辑及执行结果。
    """
    def __init__(self, storage: RelationalStorage):
        self.storage = storage

    async def record_episode(self, question: str, action_chain: Dict[str, Any], importance: float = 0.5):
        """
        记录一次审计情景（Episode）
        """
        item = MemoryItem(
            content={"question": question, **action_chain},
            memory_type="episodic",
            importance=importance,
            metadata={"timestamp": datetime.now().isoformat(), "type": "audit_action"}
        )
        await self.storage.add([item])
        logger.info(f"💾 [EpisodicMemory] 已固化审计情景: {question[:20]}...")

    async def recall_experience(self, query: str, limit: int = 3) -> List[MemoryItem]:
        """
        召回历史审计经验
        """
        logger.debug(f"🔍 [EpisodicMemory] 正在回溯相关经验: {query[:30]}...")
        return await self.storage.search(query, limit=limit)

    def format_experience_for_prompt(self, items: List[MemoryItem]) -> str:
        """
        将召回的情景格式化为 Agent 可用的经验提示词
        """
        if not items: return "尚无类似审计经验参考。"
        
        lines = ["【历史审计经验参考】"]
        for i, item in enumerate(items, 1):
            content = item.content
            q = content.get("question", "未知问题")
            method = content.get("methodology", "未知方法")
            result = "成功" if content.get("success", True) else "失败"
            lines.append(f"{i}. 问题: {q}\n   结果: {result}\n   经验建议: {method}")
            
        return "\n".join(lines)
