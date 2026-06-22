"""
业务场景探测器 - 自动识别医疗业务场景类型

解决问题：
- 不同业务场景（药店/门诊/住院）金额分布差异巨大
- 药店购药单笔通常几百元，固定10000元阈值会导致零召回
- 需要自动识别场景并选择合适的阈值策略
"""
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

import yaml
import os


@dataclass
class BusinessContext:
    """业务场景上下文"""
    business_type: str  # PHARMACY/OUTPATIENT/INPATIENT/SPECIAL_DISEASE
    business_name: str  # 中文名称
    med_type: Optional[str]  # 原始 med_type 字段值
    time_granularity: str  # SINGLE_SETL/MONTHLY/YEARLY
    table_name: str  # 主表名
    confidence: float  # 探测置信度
    detection_source: str  # METADATA/QUERY/DEFAULT


class BusinessContextDetector:
    """自动识别医疗业务场景"""

    _config: Dict[str, Any] = None

    @classmethod
    def _load_config(cls) -> Dict[str, Any]:
        """加载配置"""
        if cls._config is None:
            config_path = "configs/threshold_matrix.yaml"
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cls._config = yaml.safe_load(f)
            else:
                cls._config = {}
        return cls._config

    @classmethod
    def detect(
        cls,
        query: str,
        table_metadata: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> BusinessContext:
        """探测业务场景

        优先级：表元数据 > 查询文本 > 默认值

        Args:
            query: 用户查询文本
            table_metadata: 表元数据（包含 med_type 等）
            config: 可选的配置字典

        Returns:
            BusinessContext: 探测到的业务场景上下文
        """
        if config is None:
            config = cls._load_config()

        if table_metadata is None:
            table_metadata = {}

        scenarios = config.get("business_scenarios", {})

        # 1. 从表元数据推断（最精确）
        metadata_based = cls._detect_from_metadata(table_metadata, scenarios)

        # 2. 从查询文本推断
        query_based = cls._detect_from_query(query, scenarios)

        # 3. 合并决策：元数据优先
        final_type = metadata_based or query_based or "PHARMACY"
        detection_source = "METADATA" if metadata_based else "QUERY" if query_based else "DEFAULT"

        # 4. 获取场景配置
        scenario_config = scenarios.get(final_type, {})

        # 5. 推断时间粒度
        time_granularity = cls._detect_time_granularity(query)

        # 6. 获取置信度
        confidence = cls._calculate_confidence(
            metadata_based, query_based, detection_source
        )

        logger.info(
            f"🔍 [BusinessContext] 业务场景探测: "
            f"metadata={metadata_based}, query={query_based}, "
            f"final={final_type}({scenario_config.get('name', '未知')}), "
            f"granularity={time_granularity}, source={detection_source}"
        )

        return BusinessContext(
            business_type=final_type,
            business_name=scenario_config.get("name", "未知场景"),
            med_type=table_metadata.get("med_type"),
            time_granularity=time_granularity,
            table_name=table_metadata.get("table_name", "fqz_gz_jzsj_all_ql"),
            confidence=confidence,
            detection_source=detection_source
        )

    @classmethod
    def _detect_from_metadata(
        cls,
        table_metadata: Dict[str, Any],
        scenarios: Dict[str, Any]
    ) -> Optional[str]:
        """从表元数据推断业务场景

        通过 med_type 字段判断业务类型
        """
        med_type = table_metadata.get("med_type", "")
        table_desc = table_metadata.get("description", "")

        # 检查 med_type 字段
        for scenario_id, scenario in scenarios.items():
            patterns = scenario.get("med_type_patterns", [])
            for pattern in patterns:
                if pattern.lower() in str(med_type).lower():
                    return scenario_id

        # 检查表描述
        for scenario_id, scenario in scenarios.items():
            patterns = scenario.get("med_type_patterns", [])
            for pattern in patterns:
                if pattern.lower() in str(table_desc).lower():
                    return scenario_id

        return None

    @classmethod
    def _detect_from_query(
        cls,
        query: str,
        scenarios: Dict[str, Any]
    ) -> Optional[str]:
        """从查询文本推断业务场景

        通过用户查询中的关键词判断业务类型
        """
        query_lower = query.lower()

        for scenario_id, scenario in scenarios.items():
            patterns = scenario.get("med_type_patterns", [])
            for pattern in patterns:
                if pattern.lower() in query_lower:
                    return scenario_id

        return None

    @classmethod
    def _detect_time_granularity(cls, query: str) -> str:
        """推断时间粒度

        根据用户查询中的时间相关词汇判断
        """
        if any(kw in query for kw in ["单次", "单笔", "每次", "一次"]):
            return "SINGLE_SETL"
        elif any(kw in query for kw in ["月", "月度", "每月", "按月"]):
            return "MONTHLY"
        elif any(kw in query for kw in ["年", "年度", "每年", "按年"]):
            return "YEARLY"
        else:
            return "SINGLE_SETL"  # 默认单次

    @classmethod
    def _calculate_confidence(
        cls,
        metadata_based: Optional[str],
        query_based: Optional[str],
        detection_source: str
    ) -> float:
        """计算探测置信度"""
        if detection_source == "METADATA":
            return 0.9
        elif detection_source == "QUERY":
            return 0.7
        else:
            return 0.5


# 便捷函数
def detect_business_context(
    query: str,
    table_metadata: Optional[Dict[str, Any]] = None
) -> BusinessContext:
    """探测业务场景的便捷函数"""
    return BusinessContextDetector.detect(query, table_metadata)
