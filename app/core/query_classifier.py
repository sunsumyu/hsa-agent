from typing import Dict, Any, List, Optional
from enum import Enum
import yaml
import os
from loguru import logger

class QueryType(str, Enum):
    RANKING = "RANKING"
    AGGREGATION = "AGGREGATION"
    THRESHOLD_FILTER = "THRESHOLD_FILTER"
    COUNT_BASED = "COUNT_BASED"
    COMPARISON = "COMPARISON"
    TOP_N = "TOP_N"

class QueryClassifier:
    """问题类型分类器，根据规则与配置自动对审计提问进行分类分类"""

    DEFAULT_PATTERNS = {
        "RANKING": ["排名", "排前", "前几", "列出", "top", "排行", "从高到低", "从低到高", "排序"],
        "AGGREGATION": ["汇总", "总计", "累计", "总额", "合计", "一共"],
        "THRESHOLD_FILTER": ["大于", "超过", "高于", "异常", "大额", "高额", "异常大", "巨额", "不正常", "较多"],
        "COUNT_BASED": ["多少", "几个", "数量", "频次", "次数", "统计"],
        "COMPARISON": ["相比", "对比", "高于", "低于", "大于", "小于"],
        "TOP_N": ["前10", "前20", "前50", "前100", "top10", "top20", "top50", "top100"]
    }

    def __init__(self, config_path: str = "configs/threshold_matrix.yaml"):
        self.config_path = config_path
        self.patterns = self._load_patterns()

    def _load_patterns(self) -> Dict[str, List[str]]:
        """从阈值矩阵配置文件加载分类关键字特征"""
        patterns = self.DEFAULT_PATTERNS.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    pref_mapping = config.get("statistical_preference_mapping", {})
                    for pref, mapping in pref_mapping.items():
                        keywords = mapping.get("keywords", [])
                        if keywords:
                            patterns[pref] = [k.lower() for k in keywords]
                logger.info(f"📊 [QueryClassifier] 成功从 {self.config_path} 加载分类模式。")
            except Exception as e:
                logger.warning(f"⚠️ [QueryClassifier] 读取配置文件失败，使用默认分类模式: {e}")
        return patterns

    def classify(self, query: str) -> QueryType:
        """根据查询文本返回问题类型，指导后续分析流向 (Matt Pocock Deep Module)"""
        if not query:
            return QueryType.THRESHOLD_FILTER
            
        query_lower = query.lower()

        # 1. 优先匹配 TOP_N（更具体）
        for kw in self.patterns.get("TOP_N", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.TOP_N} (命中的关键词: '{kw}')")
                return QueryType.TOP_N

        # 2. 结合 ArchetypeRegistry 领域任务原型 (Locality for Maintainers)
        try:
            from app.core.registry.archetype_registry import archetype_registry, ArchetypeCategory
            primary_arch = archetype_registry.get_primary_archetype(query_lower)
            if primary_arch:
                if primary_arch.category == ArchetypeCategory.RANKING:
                    logger.info(f"🚦 [QueryClassifier] 命中领域任务原型 RANKING -> {QueryType.RANKING}")
                    return QueryType.RANKING
                elif primary_arch.category == ArchetypeCategory.RECONCILIATION:
                    logger.info(f"🚦 [QueryClassifier] 命中领域任务原型 RECONCILIATION -> {QueryType.AGGREGATION}")
                    return QueryType.AGGREGATION
                elif primary_arch.category == ArchetypeCategory.INVENTORY:
                    if any(w in query_lower for w in ["多少", "几个", "数量", "统计", "count"]):
                        logger.info(f"🚦 [QueryClassifier] 命中领域任务原型 INVENTORY -> {QueryType.COUNT_BASED}")
                        return QueryType.COUNT_BASED
                    logger.info(f"🚦 [QueryClassifier] 命中领域任务原型 INVENTORY -> {QueryType.AGGREGATION}")
                    return QueryType.AGGREGATION
        except Exception as e:
            logger.debug(f"[QueryClassifier] 原型查询类型判断跳过: {e}")

        # 3. 匹配 RANKING
        for kw in self.patterns.get("RANKING", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.RANKING} (命中的关键词: '{kw}')")
                return QueryType.RANKING

        # 4. 匹配 AGGREGATION
        for kw in self.patterns.get("AGGREGATION", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.AGGREGATION} (命中的关键词: '{kw}')")
                return QueryType.AGGREGATION

        # 5. 匹配 COMPARISON
        for kw in self.patterns.get("COMPARISON", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.COMPARISON} (命中的关键词: '{kw}')")
                return QueryType.COMPARISON

        # 6. 匹配 COUNT_BASED
        for kw in self.patterns.get("COUNT_BASED", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.COUNT_BASED} (命中的关键词: '{kw}')")
                return QueryType.COUNT_BASED

        # 7. 默认匹配 THRESHOLD_FILTER
        for kw in self.patterns.get("THRESHOLD_FILTER", []):
            if kw in query_lower:
                logger.info(f"🚦 [QueryClassifier] 问题分类: {QueryType.THRESHOLD_FILTER} (命中的关键词: '{kw}')")
                return QueryType.THRESHOLD_FILTER

        logger.info(f"🚦 [QueryClassifier] 无明确关键词命中，使用默认分类: {QueryType.THRESHOLD_FILTER}")
        return QueryType.THRESHOLD_FILTER

# 单例导出
query_classifier = QueryClassifier()

