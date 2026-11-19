"""
SQL Field Sanitizer Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates defensive SQL field
rewriting, strict SELECT AS alias protection, and multi-tier fuzzy matching.
"""
import re
from typing import Tuple, List, Optional
from loguru import logger
from app.infra.field_alias_catalog import FieldAliasCatalog


class SQLFieldSanitizer:
    """SQL 物理字段安全纠错与别名保护深模块"""

    def __init__(self, catalog: Optional[FieldAliasCatalog] = None):
        self.catalog = catalog or FieldAliasCatalog()

    def sanitize_sql(self, sql: str) -> Tuple[str, List[str]]:
        """
        [V119.1] 工业级纠错：扫描 SQL 中的禁用字段名并替换，但【严格保护别名】。
        """
        if not sql or not sql.strip():
            return sql, []

        warnings = []
        fixed = sql

        # 提取当前 SQL 中所有显式定义的 SELECT 别名 (如 AS total_amount, AS drug_name)
        defined_aliases = {
            m.lower() for m in re.findall(r"\bAS\s+([a-zA-Z0-9_]+)\b", sql, re.IGNORECASE)
        }

        def _safe_replace(target_sql: str, forbidden_word: str, canonical_word: str) -> str:
            # 若目标词本身就是本查询定义的输出列别名，禁止替换（避免破坏 GROUP BY / ORDER BY 中的别名引用）
            if forbidden_word.lower() in defined_aliases:
                return target_sql

            # 使用正则捕获组：(AS 关键字)? + (目标词)
            pattern = r"(\bAS\s+)?\b" + re.escape(forbidden_word) + r"\b"

            def _sub_func(match):
                if match.group(1):  # 命中了 AS 别名定义
                    return match.group(0)  # 原样返回，不纠错
                return canonical_word

            new_sql = re.sub(pattern, _sub_func, target_sql, flags=re.IGNORECASE)
            return new_sql

        # 第一阶段：纠错禁用别名
        for forbidden in self.catalog.forbidden_set:
            if re.search(r"\b" + re.escape(forbidden) + r"\b", fixed, re.IGNORECASE):
                canonical = self.catalog.forbidden_map.get(forbidden) or self.catalog.alias_map.get(forbidden)
                if canonical:
                    new_fixed = _safe_replace(fixed, forbidden, canonical)
                    if new_fixed != fixed:
                        fixed = new_fixed
                        msg = f"[FieldKG] 自动纠错: {forbidden} -> {canonical}"
                        warnings.append(msg)
                        logger.warning(msg)

        # 第二阶段：对齐普通别名 (同样保护 AS)
        for alias, canonical in self.catalog.alias_map.items():
            if alias in self.catalog.forbidden_set:
                continue
            fixed = _safe_replace(fixed, alias, canonical)

        return fixed, warnings
