"""
app/core/memory/storage/relational.py
=====================================
[V178.4] 关系型存储后端 (SQLite Relational Storage)
"""

import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime
from app.core.memory.base import MemoryItem, BaseStorage

class RelationalStorage(BaseStorage):
    def __init__(self, db_path: str = "data/memory_v3/episodic.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    memory_type TEXT,
                    importance REAL,
                    metadata TEXT,
                    timestamp TEXT
                )
            """)
            # 索引优化
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON memory_items(memory_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_items(timestamp)")

    async def add(self, items: List[MemoryItem]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for item in items:
                cursor.execute(
                    "INSERT OR REPLACE INTO memory_items VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        item.metadata.get("id", str(id(item))), 
                        json.dumps(item.content, ensure_ascii=False),
                        item.memory_type,
                        item.importance,
                        json.dumps(item.metadata, ensure_ascii=False),
                        item.timestamp.isoformat()
                    )
                )
            conn.commit()

    async def search(self, query: str, limit: int = 10) -> List[MemoryItem]:
        """
        [V178.4] 关系型检索：支持简单的关键词模糊匹配
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_items WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(MemoryItem(
                    content=json.loads(row["content"]),
                    memory_type=row["memory_type"],
                    importance=row["importance"],
                    metadata=json.loads(row["metadata"]),
                    timestamp=datetime.fromisoformat(row["timestamp"])
                ))
            return results

    def clear(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._init_db()
