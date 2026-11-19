"""
阈值决策引擎 - 企业级动态阈值策略核心

解决问题：
- 药店场景固定10000元阈值导致零召回
- 门诊/住院场景应使用不同阈值
- 用户指定阈值时直接使用，不做过度调整
- 排名类查询不需要阈值过滤
- 基线计算失败时有降级策略
"""
import yaml
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from .threshold_intent_parser import ThresholdIntent
from .business_context_detector import BusinessContext


@dataclass
class ThresholdDecision:
    """阈值决策结果"""
    strategy: str  # 策略名
    hard_threshold: Optional[float]  # 固定阈值值
    quantile: Optional[float]  # 分位数
    baseline_sql: Optional[str]  # Phase 1 基线 SQL
    reason: str  # 决策理由（人类可读）
    safety_bounds: Dict[str, float]  # 安全边界
    confidence: float  # 决策置信度
    fallback_threshold: Optional[float] = None  # 降级默认阈值
    anomaly_degree: str = ""  # 原始异常程度
    business_type: str = ""  # 业务场景


class ThresholdDecisionEngine:
    """企业级阈值决策引擎

    决策流程：
    1. 用户指定阈值 → 直接使用（应用安全边界）
    2. 排名类查询 → 不强制阈值
    3. 根据业务场景 + 异常程度 → 选择动态分位数或固定阈值
    """

    @classmethod
    def _load_config(cls) -> Dict[str, Any]:
        """加载配置（委托 threshold_config_provider）"""
        from .threshold_config_provider import get_threshold_config
        return get_threshold_config()

    @classmethod
    def _default_config(cls) -> Dict[str, Any]:
        """默认配置（委托 threshold_config_provider）"""
        from .threshold_config_provider import get_default_config
        return get_default_config()

    @classmethod
    def decide(
        cls,
        intent: ThresholdIntent,
        context: BusinessContext,
        table_metadata: Optional[Dict[str, Any]] = None
    ) -> ThresholdDecision:
        """做出阈值决策

        Args:
            intent: 阈值意图
            context: 业务场景上下文
            table_metadata: 可选的表元数据

        Returns:
            ThresholdDecision: 阈值决策结果
        """
        config = cls._load_config()

        logger.info(
            f"🧠 [ThresholdEngine] 开始阈值决策: "
            f"degree={intent.anomaly_degree}, "
            f"business={context.business_type}, "
            f"preference={intent.statistical_preference}"
        )

        # ── 规则 1: 用户指定阈值 → 直接使用 ──
        if intent.anomaly_degree == "USER_SPECIFIED" and intent.user_threshold:
            decision = cls._create_user_threshold_decision(
                intent.user_threshold, context, config
            )
            cls._log_decision(decision)
            return decision

        # ── 规则 2: 排名类查询 → 不强制阈值 ──
        if intent.statistical_preference in ("RANKING", "TOP_N"):
            decision = cls._create_ranking_decision(intent, context, config)
            cls._log_decision(decision)
            return decision

        # ── 规则 3: 根据业务场景 + 异常程度决策 ──
        decision = cls._create_dynamic_decision(intent, context, config, table_metadata)
        cls._log_decision(decision)
        return decision

    @classmethod
    def _create_user_threshold_decision(
        cls,
        threshold: float,
        context: BusinessContext,
        config: Dict[str, Any]
    ) -> ThresholdDecision:
        """规则 1: 用户指定阈值决策"""
        bounds = config.get("safety_bounds", {})
        min_bounds = bounds.get("min_threshold_by_scenario", {})
        max_bounds = bounds.get("max_threshold_by_scenario", {})

        min_t = min_bounds.get(context.business_type, bounds.get("global_min", 10))
        max_t = max_bounds.get(context.business_type, bounds.get("global_max", 1000000))

        # 应用安全边界
        final_threshold = max(min_t, min(max_t, threshold))

        was_adjusted = final_threshold != threshold

        reason = f"用户明确指定阈值 {threshold}元"
        if was_adjusted:
            reason += f"，经安全边界调整后为 {final_threshold}元"
            reason += f"（边界范围: [{min_t}, {max_t}]）"

        return ThresholdDecision(
            strategy="HARD_THRESHOLD_USER_SPECIFIED",
            hard_threshold=final_threshold,
            quantile=None,
            baseline_sql=None,
            reason=reason,
            safety_bounds={"min": min_t, "max": max_t},
            confidence=0.95,
            fallback_threshold=cls._get_fallback_threshold(context.business_type, config),
            anomaly_degree="USER_SPECIFIED",
            business_type=context.business_type
        )

    @classmethod
    def _create_ranking_decision(
        cls,
        intent: ThresholdIntent,
        context: BusinessContext,
        config: Dict[str, Any]
    ) -> ThresholdDecision:
        """规则 2: 排名类查询决策

        排名类查询只需要按金额排序，不需要阈值过滤。
        但仍然计算基线值用于辅助判断（如"是否为异常"）。
        """
        # 即使是排名类查询，也计算基线值作为参考
        quantile = cls._get_quantile_for_degree(intent.anomaly_degree, config)
        baseline_sql = cls._build_baseline_sql(quantile, context, config)

        return ThresholdDecision(
            strategy="RANKING_NO_THRESHOLD",
            hard_threshold=None,
            quantile=quantile,
            baseline_sql=baseline_sql,  # 仍然计算基线作为参考
            reason=f"排名类查询({intent.statistical_preference})，按金额排序即可，不强制阈值过滤;"
                   f"基线参考值(P{int(quantile * 100)})将作为辅助判断依据",
            safety_bounds=cls._get_safety_bounds(context.business_type, config),
            confidence=0.9,
            fallback_threshold=cls._get_fallback_threshold(context.business_type, config),
            anomaly_degree=intent.anomaly_degree,
            business_type=context.business_type
        )

    @classmethod
    def _create_dynamic_decision(
        cls,
        intent: ThresholdIntent,
        context: BusinessContext,
        config: Dict[str, Any],
        table_metadata: Optional[Dict[str, Any]]
    ) -> ThresholdDecision:
        """规则 3: 动态阈值决策

        根据业务场景策略和异常程度综合决策
        """
        scenarios = config.get("business_scenarios", {})
        quantile_config = config.get("quantile_strategies", {})

        # 1. 获取业务场景配置
        scenario_config = scenarios.get(context.business_type, {})
        scenario_strategy = scenario_config.get("threshold_strategy", "DYNAMIC_QUANTILE")

        # 2. 获取异常程度对应的分位数
        quantile = cls._get_quantile_for_degree(intent.anomaly_degree, config)

        # 3. 业务场景可能覆盖分位数
        scenario_quantile = quantile_config.get("by_business_scenario", {}).get(
            context.business_type, {}
        ).get("default")
        if scenario_quantile:
            quantile = scenario_quantile

        # 4. 时间粒度可能调整分位数
        granularity_quantile = quantile_config.get("by_time_granularity", {}).get(
            context.time_granularity, {}
        ).get("default")
        if granularity_quantile:
            quantile = granularity_quantile

        # 5. 决策策略
        if scenario_strategy == "DYNAMIC_QUANTILE":
            # 强制使用动态分位数（药店场景）
            strategy = f"DYNAMIC_QUANTILE_P{int(quantile * 100)}"
            hard_threshold = None

        elif scenario_strategy == "HARD_THRESHOLD_OR_DYNAMIC":
            # 优先固定阈值，但可动态（住院场景）
            hard_threshold = scenario_config.get("default_hard_threshold", 10000)
            strategy = "HARD_THRESHOLD"
            # 但仍生成 baseline_sql 以备降级

        else:
            # 混合策略
            strategy = f"DYNAMIC_QUANTILE_P{int(quantile * 100)}"
            hard_threshold = scenario_config.get("default_hard_threshold")

        # 6. 生成 Phase 1 基线 SQL
        baseline_sql = cls._build_baseline_sql(quantile, context, config, table_metadata)

        # 7. 构建决策理由
        reason = cls._build_decision_reason(
            strategy, quantile, hard_threshold,
            context, intent, scenario_config
        )

        return ThresholdDecision(
            strategy=strategy,
            hard_threshold=hard_threshold,
            quantile=quantile,
            baseline_sql=baseline_sql,
            reason=reason,
            safety_bounds=cls._get_safety_bounds(context.business_type, config),
            confidence=context.confidence * intent.confidence,
            fallback_threshold=cls._get_fallback_threshold(context.business_type, config),
            anomaly_degree=intent.anomaly_degree,
            business_type=context.business_type
        )

    @classmethod
    def _get_quantile_for_degree(cls, degree: str, config: Dict[str, Any]) -> float:
        """获取异常程度对应的分位数 (委托 threshold_config_provider)"""
        from .threshold_config_provider import get_quantile_for_degree
        return get_quantile_for_degree(degree, config)

    @classmethod
    def _build_baseline_sql(
        cls,
        quantile: float,
        context: BusinessContext,
        config: Dict[str, Any],
        table_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建 Phase 1 基线 SQL (委托 threshold_config_provider)"""
        from .threshold_config_provider import build_baseline_sql
        return build_baseline_sql(quantile, context, config, table_metadata)

    @classmethod
    def _get_safety_bounds(cls, business_type: str, config: Dict[str, Any]) -> Dict[str, float]:
        """获取安全边界 (委托 threshold_config_provider)"""
        from .threshold_config_provider import get_safety_bounds
        return get_safety_bounds(business_type, config)

    @classmethod
    def _get_fallback_threshold(cls, business_type: str, config: Dict[str, Any]) -> float:
        """获取降级默认阈值 (委托 threshold_config_provider)"""
        from .threshold_config_provider import get_fallback_threshold
        return get_fallback_threshold(business_type, config)

    @classmethod
    def _build_decision_reason(
        cls,
        strategy: str,
        quantile: float,
        hard_threshold: Optional[float],
        context: BusinessContext,
        intent: ThresholdIntent,
        scenario_config: Dict[str, Any]
    ) -> str:
        """构建决策理由 (委托 threshold_config_provider)"""
        from .threshold_config_provider import build_decision_reason
        return build_decision_reason(strategy, quantile, hard_threshold, context, intent, scenario_config)

    @classmethod
    def _log_decision(cls, decision: ThresholdDecision):
        """记录决策日志"""
        logger.info(
            f"🧠 [ThresholdDecision] 阈值决策完成: "
            f"strategy={decision.strategy}, "
            f"quantile={decision.quantile}, "
            f"hard_threshold={decision.hard_threshold}, "
            f"business_type={decision.business_type}, "
            f"confidence={decision.confidence:.2f}"
        )

        if decision.baseline_sql:
            logger.info(
                f"📊 [ThresholdDecision] Phase 1 基线SQL: {decision.baseline_sql}"
            )


# 便捷函数
def decide_threshold(
    query: str,
    table_metadata: Optional[Dict[str, Any]] = None
) -> ThresholdDecision:
    """阈值决策的便捷函数

    一站式完成：意图解析 → 场景探测 → 阈值决策
    """
    from .threshold_intent_parser import ThresholdIntentParser
    from .business_context_detector import BusinessContextDetector

    intent = ThresholdIntentParser.parse(query)
    context = BusinessContextDetector.detect(query, table_metadata or {})
    decision = ThresholdDecisionEngine.decide(intent, context, table_metadata)

    return decision
