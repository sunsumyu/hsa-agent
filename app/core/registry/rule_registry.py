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
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from loguru import logger


_REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "configs").is_dir()),
    Path(__file__).resolve().parent.parent.parent.parent,
)
_CONFIGS_DIR = _REPO_ROOT / "configs"
_RULES_DIR = _CONFIGS_DIR / "rules"


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
    """从 rules/sql_templates.yaml 加载所有 SQL 模板。

    并发契约: 双重检查锁 + 局部构建整体替换 (与 SchemaRegistry 同款)。
    缓存引用只被原子替换、从不清空, 读取方永远看不到中途的空缓存。
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        self._dir = rules_dir or _RULES_DIR
        self._cache: Dict[str, SQLTemplateEntry] = {}
        self._loaded = False
        self._lock = threading.Lock()

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
        """强制重新加载。

        与首次加载共用同一把锁; 先在锁内构建完整新缓存再整体替换引用,
        reload 窗口内并发读取方要么看到完整旧缓存, 要么看到完整新缓存,
        不会读到中途被清空的空缓存 (旧实现先 clear 再重载, get 会拿到 None)。
        """
        with self._lock:
            self._cache = self._load_all()
            self._loaded = True

    def _ensure_loaded(self) -> None:
        """惰性加载守卫 (双重检查锁)。"""
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return
            self._cache = self._load_all()
            self._loaded = True

    def _load_all(self) -> Dict[str, SQLTemplateEntry]:
        """实际加载逻辑; 调用方必须持有 self._lock。构建局部缓存并整体返回。"""
        cache: Dict[str, SQLTemplateEntry] = {}

        yaml_path = self._dir / "sql_templates.yaml"
        if not yaml_path.exists():
            logger.warning(f"[RuleRegistry] SQL templates not found: {yaml_path}")
            return cache

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for rule_id, rule_data in data.get("templates", {}).items():
                cache[rule_id.upper()] = SQLTemplateEntry(rule_id.upper(), rule_data)

            logger.info(
                f"[RuleRegistry] Loaded {len(cache)} SQL templates from {yaml_path}"
            )
        except Exception as e:
            logger.error(f"[RuleRegistry] Failed to load SQL templates: {e}")

        return cache


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
    """从 configs/routing_rules.yaml 加载路由规则。

    并发契约: 双重检查锁 + 局部构建整体替换。
    旧实现 _ensure_loaded 对 _rules 直接 append 且从不清空, 并发首载会产出
    重复路由规则 (业务结果错误); reload 先 clear 再重载, 会让遍历方静默跳过元素。
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or (_CONFIGS_DIR / "routing_rules.yaml")
        self._rules: List[RoutingRuleEntry] = []
        self._loaded = False
        self._lock = threading.Lock()

    def get_rules(self) -> List[RoutingRuleEntry]:
        """返回规则快照 (浅拷贝): 调用方遍历时并发 reload 不受影响, 也无法误改注册表。"""
        self._ensure_loaded()
        return list(self._rules)

    def get_rules_as_dicts(self) -> List[Dict]:
        """返回字典列表, 兼容 FastAuditRouter 现有接口。"""
        self._ensure_loaded()
        rules = self._rules  # 引用快照读: reload 只整体替换, 迭代期间不会原地清空
        return [
            {
                "target_id": r.target_id,
                "route_type": r.route_type,
                "exact_keywords": r.exact_keywords,
                "fuzzy_groups": r.fuzzy_groups,
                "description": r.description,
            }
            for r in rules
        ]

    def reload(self) -> None:
        """先在锁内构建完整新列表再整体替换引用, reload 窗口不暴露空列表。"""
        with self._lock:
            self._rules = self._load_all()
            self._loaded = True

    def _ensure_loaded(self) -> None:
        """惰性加载守卫 (双重检查锁)。"""
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return
            self._rules = self._load_all()
            self._loaded = True

    def _load_all(self) -> List[RoutingRuleEntry]:
        """实际加载逻辑; 调用方必须持有 self._lock。构建局部列表并整体返回。"""
        rules: List[RoutingRuleEntry] = []

        if not self._path.exists():
            logger.warning(f"[RoutingRules] Config not found: {self._path}")
            return rules

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for rule_data in data.get("rules", []):
                rules.append(RoutingRuleEntry(rule_data))

            logger.info(
                f"[RoutingRules] Loaded {len(rules)} routing rules from {self._path}"
            )
        except Exception as e:
            logger.error(f"[RoutingRules] Failed to load routing rules: {e}")

        return rules


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
