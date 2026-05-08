import sqlglot
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

sql_validator = SQLLogicValidator()
