"""
app/core/threshold/threshold_config_provider.py
===============================================
[Deep Module] 医保阈值决策矩阵配置、基线 SQL 与解释生成深模块

遵循 Matt Pocock 的 Deep Module 原则 (Narrow Interface, Deep Implementation):
- 窄接口:
    - get_threshold_config()
    - get_default_config()
    - get_quantile_for_degree(degree)
    - get_safety_bounds(business_type)
    - get_fallback_threshold(business_type)
    - build_baseline_sql(quantile, context, table_metadata)
    - build_decision_reason(strategy, quantile, hard_threshold, context, intent)
- 深实现:
    - 统一单例读取 configs/threshold_matrix.yaml 并处理全量默认策略回退
    - 消除 threshold_decision_engine 和 threshold_intent_parser 间的重复配置硬编码
    - 封装 Phase 1 分位数基线 ClickHouse SQL 模板动态渲染与场景适配
    - 封装多级业务场景安全边界 [{min, max}] 与降级底线计算
    - 封装决策原因可解释性文本格式化
"""

from __future__ import annotations
import os
import yaml
from typing import Dict, Any, Optional
from loguru import logger


_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def get_default_config() -> Dict[str, Any]:
    """全量内置默认阈值矩阵配置"""
    return {
        "business_scenarios": {
            "PHARMACY": {
                "name": "药店购药",
                "threshold_strategy": "DYNAMIC_QUANTILE",
                "hard_threshold_recommended": False,
                "description": "定点零售药店购药场景，金额通常较低"
            },
            "OUTPATIENT": {
                "name": "门诊就医",
                "threshold_strategy": "DYNAMIC_QUANTILE_OR_HARD",
                "hard_threshold_recommended": True,
                "default_hard_threshold": 5000,
                "description": "门诊就医场景，金额中等"
            },
            "INPATIENT": {
                "name": "住院就医",
                "threshold_strategy": "HARD_THRESHOLD_OR_DYNAMIC",
                "hard_threshold_recommended": True,
                "default_hard_threshold": 10000,
                "description": "住院就医场景，金额较高"
            }
        },
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
        },
        "safety_bounds": {
            "min_threshold_by_scenario": {
                "PHARMACY": 50, "OUTPATIENT": 200,
                "INPATIENT": 2000, "SPECIAL_DISEASE": 100
            },
            "max_threshold_by_scenario": {
                "PHARMACY": 30000, "OUTPATIENT": 80000,
                "INPATIENT": 300000, "SPECIAL_DISEASE": 50000
            }
        },
        "fallback": {
            "baseline_calculation_failure": {
                "defaults": {
                    "PHARMACY": 300, "OUTPATIENT": 2000,
                    "INPATIENT": 8000, "SPECIAL_DISEASE": 500
                }
            }
        }
    }


def get_threshold_config(force_reload: bool = False) -> Dict[str, Any]:
    """获取阈值矩阵配置（带单例缓存）"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config_path = "configs/threshold_matrix.yaml"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    _CONFIG_CACHE = loaded
                    return _CONFIG_CACHE
        except Exception as e:
            logger.warning(f"⚠️ [ThresholdConfigProvider] 解析配置文件失败: {e}，启用默认配置")

    _CONFIG_CACHE = get_default_config()
    return _CONFIG_CACHE


def get_quantile_for_degree(degree: str, config: Optional[Dict[str, Any]] = None) -> float:
    """获取异常程度对应的分位数"""
    cfg = config or get_threshold_config()
    degree_mapping = cfg.get("anomaly_degree_mapping", {}).get("keywords_to_degree", {})
    return degree_mapping.get(degree, {}).get("quantile", 0.95)


def get_safety_bounds(business_type: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """获取指定业务场景的安全上下限边界"""
    cfg = config or get_threshold_config()
    bounds = cfg.get("safety_bounds", {})
    min_bounds = bounds.get("min_threshold_by_scenario", {})
    max_bounds = bounds.get("max_threshold_by_scenario", {})

    return {
        "min": min_bounds.get(business_type, bounds.get("global_min", 10)),
        "max": max_bounds.get(business_type, bounds.get("global_max", 1000000))
    }


def get_fallback_threshold(business_type: str, config: Optional[Dict[str, Any]] = None) -> float:
    """获取指定业务场景的基线失败降级默认阈值"""
    cfg = config or get_threshold_config()
    fallback = cfg.get("fallback", {}).get("baseline_calculation_failure", {})
    defaults = fallback.get("defaults", {})
    return defaults.get(business_type, 500)


def build_baseline_sql(
    quantile: float,
    context: Any,
    config: Optional[Dict[str, Any]] = None,
    table_metadata: Optional[Dict[str, Any]] = None
) -> str:
    """构建 Phase 1 基线查询 SQL"""
    cfg = config or get_threshold_config()
    quantile_config = cfg.get("quantile_strategies", {})
    scenario_config = quantile_config.get("by_business_scenario", {}).get(
        context.business_type, {}
    )

    template = scenario_config.get(
        "baseline_sql_template",
        quantile_config.get("default", {}).get(
            "baseline_sql_template",
            "SELECT quantile({quantile})(medfee_sumamt) AS baseline FROM {table}"
        )
    )

    return template.format(
        quantile=quantile,
        table=context.table_name
    )


def build_decision_reason(
    strategy: str,
    quantile: Optional[float],
    hard_threshold: Optional[float],
    context: Any,
    intent: Any,
    scenario_config: Optional[Dict[str, Any]] = None
) -> str:
    """构建可解释性决策理由文本"""
    sc_cfg = scenario_config or {}
    parts = [
        f"业务场景: {context.business_type}({sc_cfg.get('name', '未知')})",
        f"异常程度: {intent.anomaly_degree}",
        f"时间粒度: {context.time_granularity}",
        f"决策策略: {strategy}",
    ]

    if hard_threshold:
        parts.append(f"固定阈值: {hard_threshold}元")

    if quantile is not None:
        parts.append(f"分位数: P{int(quantile * 100)}")

    scenario_desc = sc_cfg.get("reason", "")
    if scenario_desc:
        parts.append(f"场景说明: {scenario_desc}")

    return " | ".join(parts)
