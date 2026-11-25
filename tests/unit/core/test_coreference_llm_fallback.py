# -*- coding: utf-8 -*-
"""
tests/unit/core/test_coreference_llm_fallback.py
================================================
条件式长尾指代消解兜底 (Regex First, Lightweight LLM Fallback) 单元测试：
1. 正则已命中时，绝不触发 LLM；
2. 常规无代词查询或无历史上下文时，绝不触发 LLM (0ms / 0 Token)；
3. 非取证轮次 (CHITCHAT / SECURITY_BLOCK / PREFERENCE) 绝不触发 LLM；
4. 长尾口语指代（如“第二名那个药店”、“刚才那个大夫呢？”）且有历史上下文时，触发轻量 LLM 改写；
5. LLM 异常/超时时安全降级为原句，不崩溃；
6. 编排器 orchestrate_aligner_node 端到端集成验证。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from app.core.context.coreference_rewriter import (
    ContextualQueryRewriter,
    coreference_rewriter,
)
from app.core.context.aligner_node_orchestrator import orchestrate_aligner_node


def _multi_turn_state(current_q: str):
    return {
        "user_input": current_q,
        "messages": [
            HumanMessage(content="统计 2024 年违规结算金额排名前 3 的药店"),
            AIMessage(content="排名前 3 的药店为：1. 福安康大药房；2. 康泰大药房；3. 济民大药房。"),
            HumanMessage(content=current_q),
        ],
        "accumulated_findings": [
            {
                "user_query": "统计 2024 年违规结算金额排名前 3 的药店",
                "resolved_query": "统计 2024 年违规结算金额排名前 3 的药店",
                "key_entities": ["福安康大药房", "康泰大药房"],
            }
        ],
    }


class TestCoreferenceFallbackGate:
    """门控条件测试：严格保证仅长尾指代才触发兜底"""

    def test_regex_already_resolved_skips_llm(self):
        state = _multi_turn_state("其中大额结算有哪些")
        resolved, turn_type, _ = coreference_rewriter.resolve_coreference("其中大额结算有哪些", state)
        assert resolved != "其中大额结算有哪些"
        assert coreference_rewriter.needs_llm_coreference_fallback(
            "其中大额结算有哪些", resolved, turn_type, state
        ) is False

    def test_first_turn_no_history_skips_llm(self):
        state = {"messages": [HumanMessage(content="把第二名那个药店拉出来")], "accumulated_findings": []}
        assert coreference_rewriter.needs_llm_coreference_fallback(
            "把第二名那个药店拉出来", "把第二名那个药店拉出来", ContextualQueryRewriter.TASK_QUERY, state
        ) is False

    def test_normal_complete_query_with_history_skips_llm(self):
        q = "统计各乡镇卫生院的住院费用总金额"
        state = _multi_turn_state(q)
        assert coreference_rewriter.needs_llm_coreference_fallback(
            q, q, ContextualQueryRewriter.TASK_QUERY, state
        ) is False

    @pytest.mark.parametrize(
        "turn_type",
        [
            ContextualQueryRewriter.TASK_CHITCHAT,
            ContextualQueryRewriter.TASK_PREFERENCE,
            ContextualQueryRewriter.TASK_SECURITY_BLOCK,
        ],
    )
    def test_non_query_turns_skip_llm(self, turn_type):
        q = "它是什么"
        state = _multi_turn_state(q)
        assert coreference_rewriter.needs_llm_coreference_fallback(q, q, turn_type, state) is False

    @pytest.mark.parametrize(
        "q",
        [
            "把第二名那个药店的流水拉出来",
            "刚才那个大夫呢？",
            "那家的处方明细查一下",
            "再看看",
        ],
    )
    def test_unresolved_long_tail_triggers_fallback(self, q):
        state = _multi_turn_state(q)
        assert coreference_rewriter.needs_llm_coreference_fallback(
            q, q, ContextualQueryRewriter.TASK_QUERY, state
        ) is True


class TestCoreferenceLLMFallbackExecution:
    """轻量 LLM 改写与降级行为测试"""

    @pytest.mark.asyncio
    async def test_llm_fallback_rewrites_query(self):
        q = "把第二名那个药店的流水拉出来"
        state = _multi_turn_state(q)
        mock_resp = MagicMock(content="查询康泰大药房 2024 年的结算流水明细")

        with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp) as mock_chat:
            rewritten = await coreference_rewriter.llm_fallback_rewrite(q, state)

        assert rewritten == "查询康泰大药房 2024 年的结算流水明细"
        assert mock_chat.await_count == 1
        assert mock_chat.await_args.kwargs["role"] == "planner_light"

    @pytest.mark.asyncio
    async def test_llm_fallback_graceful_degradation_on_error(self):
        q = "把第二名那个药店的流水拉出来"
        state = _multi_turn_state(q)

        with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, side_effect=RuntimeError("timeout")):
            rewritten = await coreference_rewriter.llm_fallback_rewrite(q, state)

        assert rewritten == q

    @pytest.mark.asyncio
    async def test_orchestrator_uses_rewritten_query_for_funnel(self):
        q = "把第二名那个药店的流水拉出来"
        state = _multi_turn_state(q)
        mock_resp = MagicMock(content="查询康泰大药房 2024 年的结算流水明细")

        with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp), \
             patch("app.core.context.aligner_node_orchestrator.semantic_funnel.execute_alignment_flow", new_callable=AsyncMock, return_value={}) as mock_funnel:
            out = await orchestrate_aligner_node(state)

        assert out["current_turn_query"] == "查询康泰大药房 2024 年的结算流水明细"
        mock_funnel.assert_awaited_once()
        assert mock_funnel.await_args.args[0] == "查询康泰大药房 2024 年的结算流水明细"

    @pytest.mark.asyncio
    async def test_orchestrator_skips_llm_fallback_on_normal_query(self):
        q = "查询福安康大药房 2024 年的结算流水明细"
        state = _multi_turn_state(q)

        with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.core.context.aligner_node_orchestrator.semantic_funnel.execute_alignment_flow", new_callable=AsyncMock, return_value={}):
            out = await orchestrate_aligner_node(state)

        assert out["current_turn_query"] == q
        mock_chat.assert_not_called()
