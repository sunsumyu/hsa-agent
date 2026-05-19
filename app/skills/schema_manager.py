import json
import os
from typing import List, Dict, Set
from loguru import logger
from app.infra.db_conn import get_clickhouse_client

class SchemaManager:
    """
    [V80.0 企业级] 物理 Schema 统一管理器。
    负责从数据库同步真相，并为安全拦截和 Prompt 注入提供唯一权威数据源。
    """
    CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "physical_schema_cache.json")
    
    def __init__(self):
        self._schema_cache: Dict[str, List[str]] = {}
        self._field_metadata: List[Dict] = []
        self.load_cache()

    def sync_from_db(self):
        """穿透数据库，抓取最新的字段指纹"""
        logger.info("🔄 [SchemaManager] 正在从 ClickHouse 同步物理真相...")
        client = get_clickhouse_client()
        try:
            # 1. 抓取主表及核心表的字段清单 (V128.5 新增 fqz_fymx_test)
            tables = ["fqz_gz_jzsj_all_ql", "fqz_all_yy_yd_1", "fqz_drug_mcs_info_list", "fqz_fymx_test"]
            new_cache = {}
            new_metadata = []
            
            for table in tables:
                try:
                    # [V128.7] 适配 CharsetProxy 的 List[Dict] 标准化输出
                    rows = client.query(f"DESCRIBE TABLE {table}")
                    cols = [row["name"].lower() for row in rows]
                    new_cache[table.upper()] = cols
                    
                    # 构造元数据用于 Prompt 注入
                    for row in rows:
                        new_metadata.append({
                            "field": row["name"].lower(),
                            "type": row["type"],
                            "desc": row.get("comment", row["name"]), # 使用数据库 Comment
                            "table": table
                        })
                except Exception as ex_table:
                    logger.warning(f"⚠️ [SchemaManager] 表 {table} 不存在或描述失败，已跳过: {ex_table}")
            
            self._schema_cache = new_cache
            self._field_metadata = new_metadata
            self.save_cache()
            logger.success(f"✅ [SchemaManager] 同步完成，共识别 {len(new_metadata)} 个物理字段。")
        except Exception as e:
            logger.error(f"❌ [SchemaManager] 同步失败: {e}")

    def load_cache(self):
        if os.path.exists(self.CACHE_PATH):
            try:
                with open(self.CACHE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._schema_cache = data.get("cache", {})
                    self._field_metadata = data.get("metadata", [])
            except Exception:
                self.sync_from_db()
        else:
            self.sync_from_db()

    def save_cache(self):
        os.makedirs(os.path.dirname(self.CACHE_PATH), exist_ok=True)
        with open(self.CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "cache": self._schema_cache,
                "metadata": self._field_metadata
            }, f, ensure_ascii=False, indent=2)

    def get_all_columns(self) -> Set[str]:
        """获取全量物理字段白名单"""
        all_cols = set()
        for cols in self._schema_cache.values():
            all_cols.update(cols)
        return all_cols

    def get_metadata(self) -> List[Dict]:
        return self._field_metadata

# 全局单例
schema_manager = SchemaManager()
