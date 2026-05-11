"""
app.core.schema_registry — 数据库 Schema 单一事实源
=====================================================
消灭散弹式硬编码: 表名、字段名、前缀白名单、敏感字段列表
全部从 configs/schema_registry.yaml 加载。

所有模块 (security.py, prompts, audit_rules, tools, agent_graph)
都必须从此处读取 schema 信息, 而非自行硬编码。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml
from loguru import logger


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "schema_registry.yaml"


class SchemaRegistryEntry:
    """单张表的注册信息。"""

    def __init__(self, data: Dict):
        self.name: str = data["name"]
        self.description: str = data.get("description", "")
        self.alias: str = data.get("alias", self.name)
        self.fields: List[Dict] = data.get("fields", [])
        self.field_names: Set[str] = {f["name"] for f in self.fields}
        self.partition_field: Optional[str] = data.get("partition_field")
        self.default_time_filter: Optional[str] = data.get("default_time_filter")


class SchemaRegistry:
    """
    单一事实源: 所有与数据库结构相关的信息从这里获取。

    用法:
        from app.core.schema_registry import schema_registry

        # 获取主表名
        main_table = schema_registry.get_main_table()

        # 获取所有合法表名前缀
        prefixes = schema_registry.get_valid_prefixes()

        # 获取敏感字段列表 (供脱敏用)
        sensitive = schema_registry.get_sensitive_fields()

        # 获取表的字段列表 (供 prompt 注入)
        fields = schema_registry.get_table_fields("fqz_gz_jzsj_all_ql")
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or _CONFIG_PATH
        self._config: Dict = {}
        self._tables: Dict[str, SchemaRegistryEntry] = {}
        self._loaded = False

    # ── 公共 API ──────────────────────────────────────────────

    def get_main_table(self) -> str:
        """获取主结算明细表名。"""
        self._ensure_loaded()
        return self._config.get("main_table", "fqz_gz_jzsj_all_ql")

    def get_valid_prefixes(self) -> List[str]:
        """获取合法表名前缀 (供 SQLGuardian 白名单校验)。"""
        self._ensure_loaded()
        return self._config.get("valid_table_prefixes", ["fqz_"])

    def get_sensitive_fields(self) -> Set[str]:
        """获取需脱敏的敏感字段集合。"""
        self._ensure_loaded()
        return set(self._config.get("sensitive_fields", []))

    def get_forbidden_table_names(self) -> Set[str]:
        """获取禁止使用的通用表名 (幻觉表拦截)。"""
        self._ensure_loaded()
        return set(self._config.get("forbidden_table_names", []))

    def get_table(self, table_name: str) -> Optional[SchemaRegistryEntry]:
        """按表名获取注册信息。"""
        self._ensure_loaded()
        return self._tables.get(table_name)

    def get_table_fields(self, table_name: str) -> List[Dict]:
        """获取表的字段列表。"""
        entry = self.get_table(table_name)
        return entry.fields if entry else []

    def get_all_table_names(self) -> List[str]:
        """获取所有已注册的表名。"""
        self._ensure_loaded()
        return list(self._tables.keys())

    def get_tables_summary(self) -> str:
        """生成供 Prompt 注入的表摘要文本。"""
        self._ensure_loaded()
        lines = []
        for entry in self._tables.values():
            lines.append(f"- `{entry.name}`: {entry.description}")
        return "\n".join(lines)

    def get_default_time_filter(self, table_name: Optional[str] = None) -> str:
        """获取默认时间过滤条件。"""
        self._ensure_loaded()
        if table_name:
            entry = self._tables.get(table_name)
            if entry and entry.default_time_filter:
                return entry.default_time_filter
        return self._config.get("default_time_filter", "setl_time >= '2024-01-01'")

    def get_db_engine(self) -> str:
        """获取数据库引擎类型 (clickhouse / postgresql 等)。"""
        self._ensure_loaded()
        return self._config.get("db_engine", "clickhouse")

    def get_max_execution_time(self) -> int:
        """获取 SQL 最大执行时间 (秒)。"""
        self._ensure_loaded()
        return self._config.get("max_execution_time", 30)

    def get_max_memory_usage(self) -> str:
        """获取 SQL 最大内存使用量。"""
        self._ensure_loaded()
        return self._config.get("max_memory_usage", "2000000000")

    def reload(self) -> None:
        """强制重新加载配置。"""
        self._tables.clear()
        self._config.clear()
        self._loaded = False
        self._ensure_loaded()

    # ── 内部逻辑 ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if not self._path.exists():
            logger.warning(
                f"[SchemaRegistry] Config not found at {self._path}, using defaults."
            )
            self._config = self._get_defaults()
        else:
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"[SchemaRegistry] Loaded config from {self._path}")
            except Exception as e:
                logger.error(f"[SchemaRegistry] Failed to load config: {e}")
                self._config = self._get_defaults()

        # 解析表定义
        for table_data in self._config.get("tables", []):
            entry = SchemaRegistryEntry(table_data)
            self._tables[entry.name] = entry

        self._loaded = True

    @staticmethod
    def _get_defaults() -> Dict:
        """硬编码兜底 (仅在配置文件缺失时使用)。"""
        return {
            "db_engine": "clickhouse",
            "main_table": "fqz_gz_jzsj_all_ql",
            "valid_table_prefixes": ["fqz_"],
            "sensitive_fields": ["tel", "phone", "mobile", "certno", "addr", "psn_name"],
            "forbidden_table_names": [
                "patient_info", "medical_fees", "users", "orders",
                "settlements", "disease_policy", "patient_records",
            ],
            "default_time_filter": "setl_time >= '2024-01-01'",
            "max_execution_time": 30,
            "max_memory_usage": "2000000000",
            "tables": [],
        }


# 模块级单例
schema_registry = SchemaRegistry()
