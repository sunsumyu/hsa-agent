import sqlglot
import re
from sqlglot import exp, parse_one
from loguru import logger
from typing import Tuple

class SQLLogicValidator:
    """[V54.0] AST 级 SQL 逻辑等价性校验器"""
    
    @staticmethod
    def are_equivalent(sql1: str, sql2: str, dialect: str = "clickhouse") -> Tuple[bool, str]:
        """
        [V54.1] 深度逻辑对比：通过 AST 树判断两个 SQL 是否在语义上等价。
        """
        try:
            from sqlglot.optimizer import optimize
            
            # 1. 解析并进行全量语义优化
            # transform(lambda node: ...) 用于遍历 AST 树并强制转换标识符大小写
            tree1 = parse_one(sql1, read=dialect).transform(lambda node: node.copy() if not isinstance(node, exp.Identifier) else exp.Identifier(this=node.this.lower(), quoted=node.args.get("quoted")))
            tree2 = parse_one(sql2, read=dialect).transform(lambda node: node.copy() if not isinstance(node, exp.Identifier) else exp.Identifier(this=node.this.lower(), quoted=node.args.get("quoted")))
            
            # 2. 进行语义优化
            tree1 = optimize(tree1)
            tree2 = optimize(tree2)
            
            # 3. 生成完全规范化的 SQL 字符串进行比对
            norm_sql1 = tree1.sql(dialect=dialect, normalize_functions=True, pad=0, pretty=False)
            norm_sql2 = tree2.sql(dialect=dialect, normalize_functions=True, pad=0, pretty=False)
            
            if norm_sql1 == norm_sql2:
                return True, "语义完全等价 (AST 归一化后匹配)"

            return False, f"逻辑不一致 (发现实质性差异)"

        except Exception as e:
            logger.error(f"SQL AST 解析失败: {e}")
            return False, f"解析异常: {str(e)}"

    @staticmethod
    def _load_governance_config():
        import yaml
        import os
        config_path = "configs/audit_governance.yaml"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}

    @staticmethod
    def agentic_linter(sql: str) -> Tuple[bool, str]:
        """[V150.0] 框架级 SQL 治理引擎：由外部配置驱动，支持跨项目复用"""
        sql_upper = sql.upper()
        config = SQLLogicValidator._load_governance_config()
        rules = config.get("interception_rules", [])

        # 1. 基础架构校验 (主键聚合拦截)
        if "GROUP BY" in sql_upper and any(agg in sql_upper for agg in ["COUNT", "SUM", "AVG"]):
            forbidden_pks = ["SETL_ID", "MSG_ID", "REC_ID"]
            for pk in forbidden_pks:
                if pk in sql_upper.split("GROUP BY")[-1]:
                    return False, f"❌ [架构拦截] 聚合查询禁止按唯一 ID `{pk}` 分组。"

        # 2. 动态业务规则拦截 (从 YAML 加载)
        for rule in rules:
            rule_id = rule.get("id")
            # 模糊匹配拦截逻辑
            if rule_id == "no_fuzzy_matching":
                keywords = rule.get("keywords", [])
                if "LIKE" in sql_upper and any(kw.upper() in sql_upper for kw in keywords):
                    return False, f"❌ [治理拦截] {rule.get('name')}: {rule.get('description')}"
            
            # 时间维度拦截逻辑
            if rule_id == "temporal_dimension_check":
                triggers = rule.get("trigger_keywords", [])
                if any(kw.upper() in sql_upper for kw in triggers):
                    forbidden = rule.get("forbidden_fields", [])
                    mandatory = rule.get("mandatory_fields", [])
                    if any(f.upper() in sql_upper for f in forbidden) and not any(m.upper() in sql_upper for m in mandatory):
                        return False, f"❌ [维度拦截] {rule.get('name')}: {rule.get('description')}"

        # 3. 通用安全校验
        if "JOIN" in sql_upper and " ON " not in sql_upper and " USING " not in sql_upper:
             return False, "❌ [安全拦截] JOIN 语句缺失关联条件，禁止执行潜在的笛卡尔积查询。"

        return True, ""
            
        return True, ""

sql_validator = SQLLogicValidator()
