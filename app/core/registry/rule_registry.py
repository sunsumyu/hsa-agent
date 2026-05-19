"""
app.core.registry.rule_registry — 审计规则 & SQL 模板注册器
===================================================
从 YAML/SQL 文件加载:
  - 审计规则 SQL 模板 (支持 Jinja2 风格参数化)
  - 快速路由规则 (关键词 → 算子映射)

新增规则只需添加配置文件, 无需修改 Python 源码。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from loguru import logger


_CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs"
_RULES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "rules"


# ── SQL Template Registry ─────────────────────────────────────

class SQLTemplateEntry:
    """单条 SQL 模板的元数据。"""

    def __init__(self, rule_id: str, data: Dict[str, Any]):
        self.rule_id: str = rule_id
        self.description: str = data.get("description", "")
        self.category: str = data.get("category", "rule")  # rule | algorithm
        self.sql_template: str = data["sql_template"]
        self.default_table: str = data.get("default_table", "fqz_gz_jzsj_all_ql")
        self.default_limit: int = data.get("default_limit", 50)
        self.tolerance: int = data.get("tolerance", 1000)
        self.methodology: str = data.get("methodology", "")
        self.policy_basis: str = data.get("policy_basis", "")

    def render(
        self,
        table: Optional[str] = None,
        limit: Optional[int] = None,
        time_filter: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """渲染 SQL 模板, 替换占位符。"""
        sql = self.sql_template
        sql = sql.replace("{table}", table or self.default_table)
        sql = sql.replace("{limit}", str(limit or self.default_limit))

        if time_filter and "{time_filter}" in sql:
            sql = sql.replace("{time_filter}", time_filter)

        for key, value in kwargs.items():
            sql = sql.replace(f"{{{key}}}", str(value))

        return sql


class SQLTemplateRegistry:
    """从 rules/sql_templates.yaml 加载所有 SQL 模板。"""

    def __init__(self, rules_dir: Optional[Path] = None):
        self._dir = rules_dir or _RULES_DIR
        self._cache: Dict[str, SQLTemplateEntry] = {}
        self._loaded = False

    def get(self, rule_id: str) -> Optional[SQLTemplateEntry]:
        self._ensure_loaded()
        return self._cache.get(rule_id.upper())

    def get_sql(
        self,
        rule_id: str,
        table: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """获取渲染后的 SQL, 找不到返回空字符串。"""
        entry = self.get(rule_id)
        if not entry:
            return ""
        return entry.render(table=table, limit=limit, **kwargs)

    def get_methodology(self, rule_id: str) -> str:
        entry = self.get(rule_id)
        return entry.methodology if entry else ""

    def get_tolerance(self, rule_id: str) -> int:
        entry = self.get(rule_id)
        return entry.tolerance if entry else 1000

    def list_rules(self) -> List[str]:
        self._ensure_loaded()
        return list(self._cache.keys())

    def reload(self) -> None:
        self._cache.clear()
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        yaml_path = self._dir / "sql_templates.yaml"
        if not yaml_path.exists():
            logger.warning(f"[RuleRegistry] SQL templates not found: {yaml_path}")
            self._loaded = True
            return

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for rule_id, rule_data in data.get("templates", {}).items():
                entry = SQLTemplateEntry(rule_id.upper(), rule_data)
                self._cache[rule_id.upper()] = entry

            logger.info(
                f"[RuleRegistry] Loaded {len(self._cache)} SQL templates from {yaml_path}"
            )
        except Exception as e:
            logger.error(f"[RuleRegistry] Failed to load SQL templates: {e}")

        self._loaded = True


# ── Routing Rule Registry ─────────────────────────────────────

class RoutingRuleEntry:
    """单条快速路由规则。"""

    def __init__(self, data: Dict[str, Any]):
        self.target_id: str = data["target_id"]
        self.route_type: str = data.get("route_type", "KNOWN_RULE")
        self.exact_keywords: List[str] = data.get("exact_keywords", [])
        self.fuzzy_groups: List[List[str]] = data.get("fuzzy_groups", [])
        self.description: str = data.get("description", "")


class RoutingRuleRegistry:
    """从 configs/routing_rules.yaml 加载路由规则。"""

    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or (_CONFIGS_DIR / "routing_rules.yaml")
        self._rules: List[RoutingRuleEntry] = []
        self._loaded = False

    def get_rules(self) -> List[RoutingRuleEntry]:
        self._ensure_loaded()
        return self._rules

    def get_rules_as_dicts(self) -> List[Dict]:
        """返回字典列表, 兼容 FastAuditRouter 现有接口。"""
        self._ensure_loaded()
        return [
            {
                "target_id": r.target_id,
                "route_type": r.route_type,
                "exact_keywords": r.exact_keywords,
                "fuzzy_groups": r.fuzzy_groups,
                "description": r.description,
            }
            for r in self._rules
        ]

    def reload(self) -> None:
        self._rules.clear()
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if not self._path.exists():
            logger.warning(f"[RoutingRules] Config not found: {self._path}")
            self._loaded = True
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for rule_data in data.get("rules", []):
                self._rules.append(RoutingRuleEntry(rule_data))

            logger.info(
                f"[RoutingRules] Loaded {len(self._rules)} routing rules from {self._path}"
            )
        except Exception as e:
            logger.error(f"[RoutingRules] Failed to load routing rules: {e}")

        self._loaded = True


# ── 统一门面 ──────────────────────────────────────────────────

class RuleRegistry:
    """统一入口, 聚合 SQL 模板 + 路由规则。"""

    def __init__(self):
        self.sql_templates = SQLTemplateRegistry()
        self.routing_rules = RoutingRuleRegistry()

    def reload_all(self) -> None:
        self.sql_templates.reload()
        self.routing_rules.reload()


# 模块级单例
rule_registry = RuleRegistry()
