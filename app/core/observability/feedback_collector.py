# app/core/observability/feedback_collector.py
# -*- coding: utf-8 -*-
"""
app/core/observability/feedback_collector.py
=============================================
[Matt Pocock Deep Module] 现场审计闭环反馈器 (FeedbackCollector)
将审计专家的审核采纳与修改动作绑定至具体 Trace，驱动在线评估与黄金问答集沉淀。
"""

from typing import Optional, Any
from loguru import logger

class FeedbackCollector:
    """[数据飞轮反馈器] 收集现场审计员评价并沉淀至 LangSmith"""

    def __init__(self, client: Optional[Any] = None):
        self._client = client

    def record_auditor_feedback(
        self,
        run_id: str,
        is_accepted: bool,
        feedback_category: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        """
        向 LangSmith 上报人工审计反馈 (HITL Feedback)。
        若 client 为空或上报抛出异常，安全静默放行，保证主业务可用性。
        """
        if not self._client:
            logger.debug("[FeedbackCollector] LangSmith Client 未激活，静默跳过")
            return False
        try:
            self._client.create_feedback(
                run_id=run_id,
                key="auditor_acceptance",
                score=1.0 if is_accepted else 0.0,
                value=feedback_category,
                comment=comment
            )
            return True
        except Exception as e:
            logger.warning(f"⚠️ [FeedbackCollector] 上报反馈异常: {e}")
            return False
