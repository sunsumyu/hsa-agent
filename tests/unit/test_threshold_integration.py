"""
test_threshold_integration.py
============================
验证企业级动态阈值策略集成
"""

import pytest
import sys
import os

# 确保 Python 能找到项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestThresholdIntentParser:
    """测试阈值意图解析"""

    def test_parse_user_specified_threshold(self):
        """测试解析用户指定的阈值"""
        from app.core.threshold.threshold_intent_parser import ThresholdIntentParser

        # 测试案例1：用户指定数值阈值
        query1 = "查金额超过5000元的异常结算"
        intent1 = ThresholdIntentParser.parse(query1)

        print(f"Query: {query1}")
        print(f"Intent: {intent1}")

        assert intent1.user_threshold == 5000.0
        assert intent1.anomaly_degree == "USER_SPECIFIED"
        assert intent1.confidence >= 0.9

    def test_parse_high_anomaly_keywords(self):
        """测试解析高异常程度关键词"""
        from app.core.threshold.threshold_intent_parser import ThresholdIntentParser

        query2 = "查金额排名最高的异常案件"
        intent2 = ThresholdIntentParser.parse(query2)

        print(f"Query: {query2}")
        print(f"Intent: {intent2}")

        assert intent2.anomaly_degree == "HIGH"
        assert "排名最高" in intent2.raw_keywords
        assert intent2.statistical_preference in ["RANKING", "COUNT_BASED"]

    def test_parse_ranking_preference(self):
        """测试解析排名类查询偏好"""
        from app.core.threshold.threshold_intent_parser import ThresholdIntentParser

        query3 = "列出金额前10的异常结算"
        intent3 = ThresholdIntentParser.parse(query3)

        print(f"Query: {query3}")
        print(f"Intent: {intent3}")

        assert intent3.statistical_preference == "TOP_N"


class TestBusinessContextDetector:
    """测试业务场景探测"""

    def test_detect_pharmacy_from_query(self):
        """测试从查询识别药店场景"""
        from app.core.threshold.business_context_detector import BusinessContextDetector

        query = "查药店购药的大额结算"
        context = BusinessContextDetector.detect(query, {"table_name": "test_table"})

        print(f"Query: {query}")
        print(f"Context: {context}")

        assert context.business_type == "PHARMACY"
        assert context.business_name == "药店购药"

    def test_detect_inpatient_from_query(self):
        """测试从查询识别住院场景"""
        from app.core.threshold.business_context_detector import BusinessContextDetector

        query = "查住院金额偏高的异常"
        context = BusinessContextDetector.detect(query, {"table_name": "test_table"})

        print(f"Query: {query}")
        print(f"Context: {context}")

        assert context.business_type == "INPATIENT"
        assert context.business_name == "住院就医"


class TestThresholdDecisionEngine:
    """测试阈值决策引擎"""

    def test_pharmacy_dynamic_quantile(self):
        """测试药店场景动态分位数决策"""
        from app.core.threshold import (
            ThresholdIntent,
            BusinessContext,
            ThresholdDecisionEngine
        )

        intent = ThresholdIntent(
            anomaly_degree="HIGH",
            user_threshold=None,
            statistical_preference="COUNT_BASED",
            confidence=0.8,
            raw_keywords=["排名最高"]
        )

        context = BusinessContext(
            business_type="PHARMACY",
            business_name="药店购药",
            med_type="定点药店购药",
            time_granularity="SINGLE_SETL",
            table_name="fqz_gz_jzsj_all_ql",
            confidence=0.9,
            detection_source="METADATA"
        )

        decision = ThresholdDecisionEngine.decide(intent, context)

        print(f"Decision: {decision}")

        # 药店场景应该使用动态分位数，不应该有固定阈值
        assert decision.strategy.startswith("DYNAMIC_QUANTILE")
        assert decision.hard_threshold is None
        assert decision.quantile is not None
        assert decision.baseline_sql is not None

    def test_user_threshold_override(self):
        """测试用户指定阈值覆盖"""
        from app.core.threshold import (
            ThresholdIntent,
            BusinessContext,
            ThresholdDecisionEngine
        )

        intent = ThresholdIntent(
            anomaly_degree="USER_SPECIFIED",
            user_threshold=3000.0,
            statistical_preference="COUNT_BASED",
            confidence=0.95,
            raw_keywords=[]
        )

        context = BusinessContext(
            business_type="PHARMACY",
            business_name="药店购药",
            med_type="定点药店购药",
            time_granularity="SINGLE_SETL",
            table_name="fqz_gz_jzsj_all_ql",
            confidence=0.9,
            detection_source="METADATA"
        )

        decision = ThresholdDecisionEngine.decide(intent, context)

        print(f"Decision: {decision}")

        # 用户指定阈值应该直接使用
        assert decision.strategy == "HARD_THRESHOLD_USER_SPECIFIED"
        assert decision.hard_threshold == 3000.0


class TestEndToEndIntegration:
    """测试端到端集成"""

    def test_pharmacy_scenario_no_hardcoded_threshold(self):
        """测试药店场景不使用固定阈值"""
        from app.core.threshold import (
            ThresholdIntentParser,
            BusinessContextDetector,
            ThresholdDecisionEngine
        )

        # 模拟 QA-CUST-27 场景：药店购药 + 排名最高
        query = "查最近5年单次结算金额排名最高的异常案件"

        intent = ThresholdIntentParser.parse(query)
        context = BusinessContextDetector.detect(
            query,
            {"table_name": "fqz_gz_jzsj_all_ql", "med_type": "定点药店购药"}
        )
        decision = ThresholdDecisionEngine.decide(intent, context)

        print(f"Query: {query}")
        print(f"Intent: anomaly_degree={intent.anomaly_degree}")
        print(f"Context: business_type={context.business_type}")
        print(f"Decision: strategy={decision.strategy}, quantile={decision.quantile}")

        # 【核心验证】药店场景不应该使用固定阈值
        assert decision.hard_threshold is None
        assert decision.strategy.startswith("DYNAMIC_QUANTILE") or decision.strategy == "RANKING_NO_THRESHOLD"
        print("✅ 药店场景不使用固定阈值，将使用动态分位数")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])