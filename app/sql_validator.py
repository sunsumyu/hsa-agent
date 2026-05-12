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
    def agentic_linter(sql: str) -> Tuple[bool, str]:
        """[V111.0] SQL 核心审计逻辑审查：拦截逻辑自杀与幻觉诱因"""
        sql_upper = sql.upper()
        
        # 1. 逻辑自杀检测：按唯一标识进行聚合统计 (QA-01 核心症结)
        # 如果 SQL 中包含 COUNT/SUM 等聚合函数，检查 GROUP BY 是否包含了唯一主键
        if "GROUP BY" in sql_upper and any(agg in sql_upper for agg in ["COUNT", "SUM", "AVG", "GROUPARRAY"]):
            # 物理主键或唯一 ID，按这些字段分组会导致每个组永远只有 1 条记录，从而查不出“多次”
            logic_suicide_keys = ["SETL_ID", "MSG_ID", "DET_ITEM_FEE_ID", "MDTRT_ID", "REC_ID"]
            for pk in logic_suicide_keys:
                # 检查 GROUP BY 子句中是否包含这些字段
                group_by_match = re.search(r"GROUP\s+BY\s+(.*?)(ORDER\s+BY|HAVING|LIMIT|$)", sql_upper, re.DOTALL)
                if group_by_match:
                    group_by_content = group_by_match.group(1)
                    if pk in group_by_content:
                        return False, f"❌ [逻辑自杀拦截] 检测到在聚合任务中按唯一标识 `{pk}` 分组。这会导致每个分组仅含 1 条记录，无法检出‘多次’或‘重复’行为。建议改用 `psn_no` + `toDate(setl_time)`。"

        # 2. 查全率保障：频率审计缺失 HAVING 子句
        if "COUNT(" in sql_upper and "GROUP BY" in sql_upper and "HAVING" not in sql_upper:
             # 如果是查异常频率但没写 HAVING，容易产生海量无关数据
             return False, "⚠️ [性能/逻辑风险] 检测到聚合查询缺失 HAVING 子句。对于‘多次’或‘高频’审计，必须包含 `HAVING count(...) > n` 以过滤合法记录。"

        # 3. 笛卡尔积陷阱：多表 JOIN 缺失条件
        if "JOIN" in sql_upper and " ON " not in sql_upper and " USING " not in sql_upper:
             return False, "❌ [计算爆炸拦截] 检测到 JOIN 语句缺失关联条件（ON/USING）。这将产生笛卡尔积，导致算力溢出及虚假数据幻觉。"

        # 4. 字段前缀检查 (物理真理校验)
        if "FROM" in sql_upper and "FQZ_" not in sql_upper and "V_AUDIT" not in sql_upper:
            if "SYSTEM." not in sql_upper and "INFORMATION_SCHEMA" not in sql_upper:
                return False, "❌ [物理脱节] SQL 中未发现物理表前缀（如 fqz_）。请严格遵守 Schema Registry 中的表名定义。"
            
        return True, ""

sql_validator = SQLLogicValidator()
