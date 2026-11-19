
# -*- coding: utf-8 -*-
import re
import os
import json
from typing import List, Dict, Any, Optional
from loguru import logger

class AuditRuleEngine:
    """[V125.0 企业级] 审计规则引擎：从外部知识库动态加载 SQL 算子。"""
    
    def __init__(self, kb_path="configs/audit_knowledge_base.json"):
        self.kb_path = kb_path
        self.rules = self._load_rules()

    def _load_rules(self) -> dict:
        try:
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("algorithms", {})
        except Exception as e:
            logger.error(f"加载规则库失败: {e}")
        return {}

    def get_rule_sql(self, rule_id: str, table_name: Optional[str] = None, limit: int = 1000, extra_filters: Optional[Dict[str, str]] = None) -> str:
        rule_key = rule_id.upper()
        rule = self.rules.get(rule_key)
        
        template = ""
        if rule:
            template = rule.get("sql", "")
        else:
            # [Fallback] 尝试从 rule_registry 中获取 YAML 模板
            from app.core.registry.rule_registry import rule_registry
            entry = rule_registry.sql_templates.get(rule_key)
            if entry:
                template = entry.sql_template
            else:
                logger.debug(f"算子 {rule_id} 不在规则库且在注册表中未找到")
                return ""
        
        if not template:
            return ""

        # [V125.1 企业级] 物理表名动态映射
        from app.core.registry.schema_registry import schema_registry
        header_table = schema_registry.get_main_table()
        detail_table = "fqz_fymx_test" # 默认明细表，可进 Registry
        
        try:
            sql = template.format(
                table=table_name or header_table, 
                header_table=header_table,
                detail_table=detail_table,
                limit=limit
            )
        except KeyError as e:
            logger.warning(f"模板格式化失败，缺少参数: {e}")
            sql = template
        
        # 3. 动态过滤器注入
        if extra_filters:
            # (Keeping the injection logic from the original file...)
            sql = self._inject_filters(sql, extra_filters)
            
        return sql

    def _inject_filters(self, sql: str, extra_filters: Dict[str, Any]) -> str:
        filter_clauses = []
        for k, v in extra_filters.items():
            v_str = str(v).strip()
            v_upper = v_str.upper()
            if (v_upper.startswith("LIKE") or 
                v_str.startswith(">") or 
                v_str.startswith("<") or 
                v_str.startswith("=") or 
                v_str.startswith("!=") or 
                v_str.startswith("<=") or 
                v_str.startswith(">=")):
                filter_clauses.append(f"({k} {v_str})")
            else:
                filter_clauses.append(f"({k} = '{v_str}')")
        if filter_clauses:
            combined = " AND ".join(filter_clauses)
            if "WHERE" in sql.upper():
                sql = sql.replace("WHERE", f"WHERE {combined} AND", 1)
            else:
                # Basic injection before GROUP BY or ORDER BY
                for marker in ["GROUP BY", "ORDER BY", "LIMIT"]:
                    if marker in sql.upper():
                        sql = sql.replace(marker, f"WHERE {combined} {marker}", 1)
                        break
                else:
                    sql += f" WHERE {combined}"
        return sql

    def format_violation_report(self, rule_id: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "未发现违规记录。"
        count = len(results)
        desc = self.rules.get(rule_id.upper(), {}).get("desc", rule_id)
        return f"【规则对撞】{desc} 命中 {count} 条违规线索。"

# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

rule_engine = LazyProxy("rule_engine")
