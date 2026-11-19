"""
app/core/gates.py
=================
[V154.0] 自适应质量门控 (Adaptive Quality Gates)

负责根据消息元数据和内容评估执行质量，为 LangGraph 提供动态路由依据。
"""

from typing import Dict, Any
from langchain_core.messages import BaseMessage

class QualityGate:
    """
    [Matt Pocock Deep Module / Facade]
    质量门控门面：利用审计元数据驱动自愈逻辑，为图调度提供统一门控接缝。
    """
    
    @staticmethod
    def evaluate_response(message: BaseMessage) -> float:
        """评估响应质量 (0.0 ~ 1.0)"""
        from app.core.guardrails.risk_confidence_evaluator import evaluate_response_confidence
        return evaluate_response_confidence(message)

    @staticmethod
    def evaluate_risk(state: Dict[str, Any]) -> float:
        """评估操作风险 (0.0 ~ 1.0)"""
        from app.core.guardrails.risk_confidence_evaluator import evaluate_execution_risk
        return evaluate_execution_risk(state)

    @staticmethod
    def should_trigger_human_approval(state: Dict[str, Any]) -> bool:
        """判断是否需要人工介入 (HITL)"""
        from app.core.guardrails.risk_confidence_evaluator import should_trigger_human_approval
        return should_trigger_human_approval(state)

    @staticmethod
    def should_trigger_critic(state: Dict[str, Any]) -> bool:
        """判断是否需要触发 CRITIC 自愈节点"""
        from app.core.guardrails.risk_confidence_evaluator import should_trigger_critic
        return should_trigger_critic(state)

    @staticmethod
    def validate_intent(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        [V178.10 / Matt Pocock Deep Module] Gate 1: 校验意图与方法论的一致性。
        委托至 intent_alignment_guard 深模块。
        """
        from app.core.guardrails.intent_alignment_guard import guard_intent_alignment
        return guard_intent_alignment(state)

    @staticmethod
    def validate_sql_semantics(state, sql: str) -> Dict[str, Any]:
        """
        [V178.10 / Matt Pocock Deep Module] Gate 2: SQL 语义与原型校验 — 委托至 sql_semantic_guard 深模块。

        Args:
            state: 审计状态字典
            sql: 待执行的 SQL 语句

        Returns:
            {"passed": bool, "error": str or None, "warnings": List[str]}
        """
        from app.core.guardrails.sql_semantic_guard import guard_sql_semantics
        return guard_sql_semantics(state, sql)

    @staticmethod
    def validate_result_matching(state) -> Dict[str, Any]:
        """
        [V178.10 / Matt Pocock Deep Module] Gate 3: 结果匹配校验 — 检查查询结果是否与审计目标匹配。
        委托至 result_matching_guard 深模块。
        """
        from app.core.guardrails.result_matching_guard import guard_result_matching
        return guard_result_matching(state)
