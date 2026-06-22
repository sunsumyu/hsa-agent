"""
阈值意图解析器 - 从用户自然语言解析阈值意图

解决问题：
- 用户说"大额"但没说具体多少
- 用户说"排名最高"需要识别为高异常程度
- 用户明确指定了阈值数值（如"超过5000元"）
"""
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from loguru import logger

import yaml
import os


@dataclass
class ThresholdIntent:
    """阈值意图数据结构"""
    anomaly_degree: str  # HIGH/MEDIUM/LOW/USER_SPECIFIED
    user_threshold: Optional[float]  # 用户指定的数值阈值
    statistical_preference: str  # RANKING/COUNT_BASED/AGGREGATION/COMPARISON/TOP_N
    confidence: float  # 解析置信度
    raw_keywords: List[str] = field(default_factory=list)  # 匹配到的原始关键词


class ThresholdIntentParser:
    """从用户自然语言解析阈值相关意图"""

    _config: Dict[str, Any] = None

    # 数值提取正则 - 支持多种中文表达
    NUMBER_PATTERNS = [
        # 超过/高于/大于 5000元
        re.compile(r'(?:超过|高于|大于|>=|≥|不少于|至少|大于等于)\s*(?:¥|元)?\s*(\d+(?:\.\d+)?)(?:万|千|百)?(?:元|块)?', re.IGNORECASE),
        # 5000元以上/以上5000元
        re.compile(r'(\d+(?:\.\d+)?)(?:万|千|百)?(?:元|块)?(?:以上|以上)', re.IGNORECASE),
        # 单笔超过5000
        re.compile(r'单[笔次][超达](\d+(?:\.\d+)?)(?:万|千|百)?(?:元|块)?', re.IGNORECASE),
    ]

    # 中文数字单位转换
    CN_NUMBER_MAP = {
        '万': 10000, '千': 1000, '百': 100,
        '十': 10, '元': 1, '块': 1
    }

    @classmethod
    def _load_config(cls) -> Dict[str, Any]:
        """加载配置"""
        if cls._config is None:
            config_path = "configs/threshold_matrix.yaml"
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cls._config = yaml.safe_load(f)
            else:
                logger.warning("⚠️ [ThresholdIntent] 配置文件不存在，使用默认配置")
                cls._config = cls._default_config()
        return cls._config

    @classmethod
    def _default_config(cls) -> Dict[str, Any]:
        """默认配置"""
        return {
            "anomaly_degree_mapping": {
                "keywords_to_degree": {
                    "HIGH": {
                        "keywords": ["排名最高", "最大", "极端", "异常大", "巨额", "特大", "最大额", "最高额", "排在前面"],
                        "quantile": 0.99
                    },
                    "MEDIUM": {
                        "keywords": ["大额", "高额", "异常", "偏高", "超出正常", "不正常", "疑似", "较高", "偏大"],
                        "quantile": 0.95
                    },
                    "LOW": {
                        "keywords": ["偏高", "较高", "略高", "稍微", "一点"],
                        "quantile": 0.90
                    }
                }
            },
            "statistical_preference_mapping": {
                "RANKING": {
                    "keywords": ["排名", "排前", "前几", "列出", "TOP", "排行", "从高到低", "从低到高", "排序"],
                    "threshold_optional": True
                },
                "COUNT_BASED": {
                    "keywords": ["多少", "几个", "数量", "频次", "次数", "统计"],
                    "threshold_optional": False
                },
                "TOP_N": {
                    "keywords": ["前10", "前20", "前50", "前100", "TOP10", "TOP20", "TOP50", "TOP100"],
                    "threshold_optional": True
                }
            }
        }

    @classmethod
    def parse(cls, query: str, config: Optional[Dict[str, Any]] = None) -> ThresholdIntent:
        """解析用户查询中的阈值意图

        Args:
            query: 用户自然语言查询
            config: 可选的配置字典（覆盖默认配置）

        Returns:
            ThresholdIntent: 解析出的阈值意图
        """
        if config is None:
            config = cls._load_config()

        query_lower = query.lower()

        # 1. 尝试提取用户指定的数值阈值
        user_threshold = cls._extract_user_threshold(query)

        # 2. 识别异常程度关键词
        anomaly_degree, matched_keywords = cls._detect_anomaly_degree(
            query_lower, config
        )

        # 3. 识别统计方法偏好
        statistical_preference, top_n = cls._detect_statistical_preference(
            query_lower, config
        )

        # 4. 如果用户指定了阈值，强制使用 USER_SPECIFIED
        if user_threshold is not None:
            anomaly_degree = "USER_SPECIFIED"

        # 5. 计算置信度
        confidence = cls._calculate_confidence(
            user_threshold, matched_keywords, statistical_preference
        )

        logger.info(
            f"📊 [ThresholdIntent] 解析结果: "
            f"degree={anomaly_degree}, threshold={user_threshold}, "
            f"preference={statistical_preference}, confidence={confidence:.2f}"
        )

        return ThresholdIntent(
            anomaly_degree=anomaly_degree,
            user_threshold=user_threshold,
            statistical_preference=statistical_preference,
            confidence=confidence,
            raw_keywords=matched_keywords
        )

    @classmethod
    def _extract_user_threshold(cls, query: str) -> Optional[float]:
        """提取用户指定的数值阈值

        支持格式：
        - 超过5000元
        - 高于1万
        - >=10000
        - 5000元以上
        - 单笔超过3000
        """
        for pattern in cls.NUMBER_PATTERNS:
            match = pattern.search(query)
            if match:
                num_str = match.group(1)
                value = cls._parse_chinese_number(num_str, query)

                if value and value > 0:
                    logger.info(f"📊 [ThresholdIntent] 提取用户阈值: '{match.group(0)}' -> {value}元")
                    return value

        return None

    @classmethod
    def _parse_chinese_number(cls, num_str: str, context: str) -> Optional[float]:
        """解析中文数字表达

        Examples:
            "5000" -> 5000.0
            "1万" -> 10000.0
            "5000万" -> 50000000.0
            "3千" -> 3000.0
        """
        try:
            # 基础数字
            base_value = float(re.sub(r'[^\d.]', '', num_str))

            # 检查上下文中的单位
            multiplier = 1.0
            for unit, mult in cls.CN_NUMBER_MAP.items():
                if unit in context:
                    multiplier = mult
                    break

            # 如果数字字符串本身包含单位
            if '万' in num_str:
                multiplier = 10000
            elif '千' in num_str:
                multiplier = 1000
            elif '百' in num_str:
                multiplier = 100

            return base_value * multiplier

        except (ValueError, TypeError):
            return None

    @classmethod
    def _detect_anomaly_degree(
        cls,
        query: str,
        config: Dict[str, Any]
    ) -> tuple:
        """识别异常程度关键词

        Returns:
            (anomaly_degree, matched_keywords)
        """
        degree_mapping = config.get("anomaly_degree_mapping", {}).get("keywords_to_degree", {})
        matched_keywords = []

        # 按优先级检查（HIGH > MEDIUM > LOW）
        for degree in ["HIGH", "MEDIUM", "LOW"]:
            mapping = degree_mapping.get(degree, {})
            keywords = mapping.get("keywords", [])

            for kw in keywords:
                if kw.lower() in query:
                    matched_keywords.append(kw)
                    logger.debug(f"📊 [ThresholdIntent] 匹配异常程度关键词: '{kw}' -> {degree}")
                    return degree, matched_keywords

        # 默认中等异常程度
        return "MEDIUM", matched_keywords

    @classmethod
    def _detect_statistical_preference(
        cls,
        query: str,
        config: Dict[str, Any]
    ) -> tuple:
        """识别统计方法偏好

        Returns:
            (statistical_preference, top_n_value)
        """
        pref_mapping = config.get("statistical_preference_mapping", {})

        # 检查 TOP_N
        top_n_match = re.search(r'(?:前|TOP)\s*(\d+)', query, re.IGNORECASE)
        if top_n_match:
            return "TOP_N", int(top_n_match.group(1))

        # 检查其他偏好
        for preference, mapping in pref_mapping.items():
            if preference == "TOP_N":
                continue
            keywords = mapping.get("keywords", [])
            for kw in keywords:
                if kw.lower() in query:
                    logger.debug(f"📊 [ThresholdIntent] 匹配统计偏好: '{kw}' -> {preference}")
                    return preference, None

        return "COUNT_BASED", None  # 默认

    @classmethod
    def _calculate_confidence(
        cls,
        user_threshold: Optional[float],
        matched_keywords: List[str],
        preference: str
    ) -> float:
        """计算解析置信度

        置信度规则：
        - 用户指定数值 -> 高置信度 (0.95)
        - 匹配到关键词 -> 中等置信度 (0.7 + 0.1 * 关键词数)
        - 无明确指示 -> 低置信度 (0.5)
        """
        # 用户指定数值 -> 高置信度
        if user_threshold is not None:
            return 0.95

        # 匹配到关键词 -> 中等置信度
        if matched_keywords:
            return min(0.9, 0.7 + 0.1 * len(matched_keywords))

        # TOP_N 或 RANKING -> 中等置信度
        if preference in ["TOP_N", "RANKING"]:
            return 0.8

        # 无明确指示 -> 低置信度
        return 0.5


# 便捷函数
def parse_threshold_intent(query: str) -> ThresholdIntent:
    """解析阈值意图的便捷函数"""
    return ThresholdIntentParser.parse(query)
