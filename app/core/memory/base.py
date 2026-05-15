"""
app/core/memory/base.py
=======================
[V177.0] 统一记忆基类协议 (Memory Base Protocols)

职责：
1. 定义标准记忆项 (MemoryItem)。
2. 定义存储后端 (BaseStorage) 的抽象接口。
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pydantic import BaseModel, Field

class MemoryItem(BaseModel):
    """
    统一记忆项标准：支持跨层级流转与序列化。
    """
    content: Any                    # 记忆核心内容
    memory_type: str                # episodic (情景), semantic (语义), working (工作)
    importance: float = 1.0         # 权重 (0.0 - 1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    ttl: Optional[int] = None       # 生存时间 (秒)

class BaseStorage:
    """
    存储后端抽象基类。
    """
    async def add(self, items: List[MemoryItem]):
        """持久化存储记忆项"""
        raise NotImplementedError

    async def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """根据内容检索相关记忆"""
        raise NotImplementedError

    def clear(self):
        """清理数据 (通常用于测试或重置)"""
        pass
