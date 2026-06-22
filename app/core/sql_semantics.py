import re
from typing import Dict, Any, List
from loguru import logger
from app.core.query_classifier import QueryType

class SQLSemanticsChecker:
    """SQL 语义预检查器，负责在 SQL 执行前校验聚合/排序逻辑是否符合业务提问意图"""

    def check_group_by_validity(self, sql: str, query_type: QueryType, methodology: str = "") -> Dict[str, Any]:
        """校验 GROUP BY 的合理性"""
        sql_upper = sql.upper()
        
        # 匹配 GROUP BY 子句，直到其他关键SQL字眼或结尾
        group_by_match = re.search(
            r'GROUP\s+BY\s+(.+?)(?:ORDER\s+BY|LIMIT|HAVING|UNION|SELECT|WITH|$)', 
            sql_upper, 
            re.DOTALL
        )
        
        # 1. 排名类或 Top-N 查询禁止使用 GROUP BY 聚合，但允许复合意图（如统计频次、累计金额）
        if query_type in (QueryType.RANKING, QueryType.TOP_N):
            is_composite = any(w in methodology.lower() for w in ["频繁", "频次", "次数", "累计", "汇总", "哪些", "统计", "count", "group by"])
            if group_by_match and not is_composite:
                return {
                    "passed": False,
                    "error": (
                        f"【SQL 语义错误】当前问题属于排序/Top-N查询（{query_type.value}），"
                        f"但生成的 SQL 却执行了 'GROUP BY' 聚合分组：'{group_by_match.group(0).strip()}'。 "
                        f"此类查询必须直接查询主表记录字段（如 setl_id, medfee_sumamt 等），"
                        f"然后进行 ORDER BY medfee_sumamt DESC LIMIT N，禁止使用 GROUP BY 将多笔结算压缩合并。"
                    )
                }
                
        # 2. 金额字段禁止直接作为 GROUP BY 维度（常见大模型幻觉：按金额分组计数）
        if group_by_match:
            group_by_fields = group_by_match.group(1)
            blacklisted_fields = ["MEDFEE_SUMAMT", "FUND_PAY_SUMAMT", "DET_ITEM_FEE_SUMAMT"]
            for field in blacklisted_fields:
                if re.search(rf'\b{field}\b', group_by_fields):
                    return {
                        "passed": False,
                        "error": (
                            f"【SQL 语义错误】SQL 在 'GROUP BY' 子句中将数值金额字段 '{field}' 作为了分组健。"
                            f"金额是连续型数值变量，应该使用 SUM/AVG/MAX/QUANTILE 等函数聚合，绝对不能直接作为 GROUP BY 维度分组。"
                        )
                    }

        return {"passed": True, "error": None}

    def check_aggregation_validity(self, sql: str, methodology: str) -> Dict[str, Any]:
        """校验聚合函数与方法论的一致性"""
        sql_upper = sql.upper()
        methodology_lower = methodology.lower()
        
        # 如果方法论中强调“单次结算”或“单笔大额”，但 SQL 中使用了 GROUP BY，且未包含结算键标识 (setl_id)
        if "单次结算" in methodology_lower or "单次" in methodology_lower or "单笔" in methodology_lower:
            group_by_match = re.search(
                r'GROUP\s+BY\s+(.+?)(?:ORDER\s+BY|LIMIT|HAVING|UNION|SELECT|WITH|$)', 
                sql_upper, 
                re.DOTALL
            )
            if group_by_match:
                group_by_fields = group_by_match.group(1)
                # 检查是否有 SETL_ID 字段，且没有被排除
                if "SETL_ID" not in group_by_fields:
                    return {
                        "passed": False,
                        "error": (
                            f"【SQL 语义错误】方法论中指明核查目标是『单次结算』或『单笔大额』，"
                            f"但生成的 SQL 在 GROUP BY 子句 '{group_by_fields.strip()}' 中未包含结算标识主键 'setl_id'。"
                            f"这会导致同一个患者在同一个机构的多笔结算被错配累加，混淆了单笔结算的业务特征。请务必在 GROUP BY 中加入 setl_id。"
                        )
                    }

        return {"passed": True, "error": None}

    def validate(self, sql: str, query_type: QueryType, methodology: str) -> Dict[str, Any]:
        """执行全量 SQL 语义合理性检查"""
        if not sql:
            return {"passed": True, "error": None}

        # 1. 检查 GROUP BY 的合理性
        group_res = self.check_group_by_validity(sql, query_type, methodology)
        if not group_res["passed"]:
            return group_res

        # 2. 检查聚合逻辑匹配度
        agg_res = self.check_aggregation_validity(sql, methodology)
        if not agg_res["passed"]:
            return agg_res

        return {"passed": True, "error": None}

# 单例导出
sql_semantics_checker = SQLSemanticsChecker()
