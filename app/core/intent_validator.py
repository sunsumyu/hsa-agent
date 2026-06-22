from typing import Dict, Any, List
import re
from loguru import logger
from app.core.query_classifier import QueryType

class IntentValidator:
    """意图-方法论一致性校验器，负责检验 Planner 的设计思路是否符合问题类型"""

    def validate_alignment(
        self,
        original_query: str,
        query_type: QueryType,
        methodology: str,
        threshold_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        校验点：
        1. 方法论是否匹配问题类型（RANKING 类不应有'基线计算'或'先计算分位数'等阻碍直接排序的行为）
        2. 阈值策略与业务场景的一致性（如：药店不应使用固定大额阈值）
        3. 问题类型和分组行为的匹配（排名类不应包含 GROUP BY 金额字段倾向）
        """
        passed = True
        errors = []

        methodology_lower = methodology.lower()

        # 1. 校验 RANKING/TOP_N 意图
        if query_type in (QueryType.RANKING, QueryType.TOP_N):
            forbidden_words = ["基线", "分位数", "quantile", "先计算", "计算阈值", "计算基线"]
            for word in forbidden_words:
                if word in methodology_lower:
                    passed = False
                    errors.append(
                        f"排名类/Top-N查询（{query_type.value}）方法论中包含了不必要的前置基线计算特征: '{word}'。"
                        f"此类查询应该直接对主表记录执行 ORDER BY ... DESC LIMIT N，不应包含计算分位数或基线的前置步骤。"
                    )
            
            # 排名类问题不允许包含 GROUP BY 聚合倾向，但允许复合意图（如统计频次、累计金额）
            is_composite = any(w in original_query for w in ["频繁", "频次", "次数", "累计", "汇总", "哪些医院", "哪些患者", "统计"])
            if ("分组" in methodology_lower or "group by" in methodology_lower or "聚合" in methodology_lower) and not is_composite:
                passed = False
                errors.append(
                    f"排名类/Top-N查询方法论中存在 '分组/GROUP BY/聚合' 倾向。"
                    f"这会导致每个患者的单笔结算个案被混淆为累计值，无法体现单次结算金额的最高个案。"
                )

        # 2. 校验 THRESHOLD_FILTER 意图（如药店场景）
        elif query_type == QueryType.THRESHOLD_FILTER:
            is_pharmacy = "药店" in original_query or "购药" in original_query
            if is_pharmacy:
                # 检验是否强行在方法论中引入了不符合药店常识的固定大额阈值（如大于 5000 或 10000 元）
                hard_limits = re.findall(r'(?:大于|超过|固定阈值|阈值设置为)\s*(\d+)\s*(?:元)?', methodology_lower)
                for limit in hard_limits:
                    if int(limit) >= 2000:
                        passed = False
                        errors.append(
                            f"定点药店购药场景的金额往往偏低（单次结算通常不超过几百元），"
                            f"但方法论中硬编码了过大的固定阈值 '{limit}元'。这会导致严重漏判（Recall=0），请改用动态分位数基线。"
                        )

        logger.info(f"🛡️ [IntentValidator] 校验结果: passed={passed}, errors={errors}")
        return {
            "passed": passed,
            "errors": errors,
            "msg": "; ".join(errors) if errors else "对齐一致"
        }

# 单例导出
intent_validator = IntentValidator()
