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
from app.core.memory.base import MemoryItem, BaseStorage, StorageStats

class RelationalStorage(BaseStorage):
    def __init__(self, db_path: str = "data/memory_v3/episodic.db"):
        self.db_path = db_path
        self.hits = 0
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # 1. 记忆条目表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    memory_type TEXT,
                    importance REAL,
                    metadata TEXT,
                    timestamp TEXT,
                    tenant_id TEXT
                )
            """)
            # 2. [V178.9] 系统配置同步表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS endpoint_configs (
                    id TEXT PRIMARY KEY,
                    pool_id TEXT,
                    platform TEXT,
                    model_name TEXT,
                    weight INTEGER,
                    status TEXT,
                    last_sync TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_meta (
                    config_name TEXT PRIMARY KEY,
                    last_hash TEXT,
                    update_time TEXT
                )
            """)
            
            # [V181.0] 迁移：检查并添加 tenant_id 列
            cursor = conn.execute("PRAGMA table_info(memory_items)")
            cols = [row[1] for row in cursor.fetchall()]
            if "tenant_id" not in cols:
                logger.info("🔧 [RelationalStorage] 正在执行数据库迁移：增加 tenant_id 列")
                conn.execute("ALTER TABLE memory_items ADD COLUMN tenant_id TEXT DEFAULT 'default'")

            # 索引优化
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON memory_items(memory_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_items(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON memory_items(tenant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pool ON endpoint_configs(pool_id)")

    async def add(self, items: List[MemoryItem]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for item in items:
                cursor.execute(
                    "INSERT OR REPLACE INTO memory_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.metadata.get("id", str(id(item))), 
                        json.dumps(item.content, ensure_ascii=False),
                        item.memory_type,
                        item.importance,
                        json.dumps(item.metadata, ensure_ascii=False),
                        item.timestamp.isoformat(),
                        item.metadata.get("tenant_id", "default")
                    )
                )
            conn.commit()

    async def search(self, query: str, limit: int = 10, tenant_id: str = "default") -> List[MemoryItem]:
        """
        [V181.0] 增强型关系检索：支持多租户隔离
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_items WHERE content LIKE ? AND tenant_id = ? ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", tenant_id, limit)
            )
            rows = cursor.fetchall()
            self.hits += 1
            
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

    async def delete_low_importance(self, threshold: float) -> int:
        """删除重要性低于阈值的记忆项"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_items WHERE importance < ?", (threshold,))
            count = cursor.rowcount
            conn.commit()
            return count

    async def delete_expired(self, max_age_days: int) -> int:
        """删除过期的记忆项"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # SQLite 没有内置的 ISO 时间计算，这里用简单的日期比较或在 Python 层处理
            # 假设存储的是 ISO 格式：YYYY-MM-DDTHH:MM:SS...
            from datetime import timedelta
            expire_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            cursor.execute("DELETE FROM memory_items WHERE timestamp < ?", (expire_date,))
            count = cursor.rowcount
            conn.commit()
            return count

    def get_name(self) -> str:
        return "SQLite-Relational-Storage"

    def get_stats(self) -> StorageStats:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM memory_items")
                count = cursor.fetchone()[0]
                size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                return StorageStats(
                    total_items=count,
                    storage_size_bytes=size,
                    hits=self.hits
                )
        except Exception:
            return StorageStats(health_status="error")

    def clear(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._init_db()
