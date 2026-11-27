"""
tests/unit/agents/test_coder_inference_coordinator_red.py
=========================================================
红灯测试：验证 CoderInferenceCoordinator 深模块的推理协同、协议自愈与单刀直入重试能力
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

# 待提取的深模块
from app.agents.coder_inference_coordinator import (
    coordinate_coder_inference,
    CoderInferenceResult,
)
from app.core.structured_tracer import StructuredTracer


@pytest.mark.asyncio
async def test_first_attempt_has_tool_calls():
    """验证当首次模型调用直接输出合法工具调用时，直接返回 response，不触发重试"""
    tracer = StructuredTracer(session_id="test_sess")
    prompt = [HumanMessage(content="查询医保数据")]
    state = {}
    tools = []

    mock_response = AIMessage(
        content="正在调用查询",
        tool_calls=[{"name": "execute_audit_sql", "args": {"sql": "SELECT 1"}, "id": "call_1"}]
    )

    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response

        with tracer.span("CODER_REASONING", node="CODER") as span:
            res = await coordinate_coder_inference(
                prompt=prompt,
                state=state,
                config={},
                tools=tools,
                span=span,
                tracer=tracer
            )

        assert isinstance(res, CoderInferenceResult)
        assert res.has_tool_calls is True
        assert res.direct_return_state is None
        assert res.response.tool_calls[0]["name"] == "execute_audit_sql"
        assert mock_chat.call_count == 1


@pytest.mark.asyncio
async def test_tool_call_synthesized_via_normalizer():
    """验证模型回复为 Markdown SQL 代码块时，协议网关自动自愈合成为 tool_calls，不触发强制重试"""
    tracer = StructuredTracer(session_id="test_sess")
    prompt = [HumanMessage(content="查询数据")]
    state = {}
    tools = []

    mock_response = AIMessage(
        content="这是为你编写的 SQL：\n```sql\nSELECT * FROM fqz_fymx_test LIMIT 10;\n```",
        tool_calls=[]
    )

    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response

        with tracer.span("CODER_REASONING", node="CODER") as span:
            res = await coordinate_coder_inference(
                prompt=prompt,
                state=state,
                config={},
                tools=tools,
                span=span,
                tracer=tracer
            )

        assert res.has_tool_calls is True
        assert res.direct_return_state is None
        assert len(res.response.tool_calls) > 0
        assert mock_chat.call_count == 1


@pytest.mark.asyncio
async def test_no_tool_calls_triggers_mandate_retry_success():
    """验证首次未调用工具且无历史数据时，脱水压缩并触发单刀直入强制重试"""
    tracer = StructuredTracer(session_id="test_sess")
    prompt = [HumanMessage(content="查询数据")]
    state = {"sql_history": [], "raw_data": ""}
    tools = []

    chatty_first_response = AIMessage(
        content="我认为医保数据查询需要结合多个维度进行，你具体想查询什么？" * 10,
        tool_calls=[]
    )
    retry_success_response = AIMessage(
        content="好的，立即执行物理查询",
        tool_calls=[{"name": "execute_audit_sql", "args": {"sql": "SELECT 1"}, "id": "call_retry"}]
    )

    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = [chatty_first_response, retry_success_response]

        with tracer.span("CODER_REASONING", node="CODER") as span:
            res = await coordinate_coder_inference(
                prompt=prompt,
                state=state,
                config={},
                tools=tools,
                span=span,
                tracer=tracer
            )

        assert res.has_tool_calls is True
        assert res.direct_return_state is None
        assert mock_chat.call_count == 2
        # 验证第二轮 prompt 包含强制执行指令
        second_call_messages = mock_chat.call_args_list[1].kwargs["messages"]
        assert any("【强制执行指令】" in str(getattr(m, "content", "")) for m in second_call_messages)


@pytest.mark.asyncio
async def test_no_tool_calls_both_attempts_direct_return():
    """验证两轮重试均未触发工具时，安全组装直接回复字典，保全已有取证成果或输出错误日志"""
    tracer = StructuredTracer(session_id="test_sess")
    prompt = [HumanMessage(content="查询数据")]
    state = {
        "sql_history": ["SELECT count(*) FROM fqz_gz_jzsj_all_ql"],
        "raw_data": '[{"count": 100}]',
        "sql_validated": True,
    }
    tools = []

    chatty_response = AIMessage(content="请确认查询口径", tool_calls=[])

    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = chatty_response

        with tracer.span("CODER_REASONING", node="CODER") as span:
            res = await coordinate_coder_inference(
                prompt=prompt,
                state=state,
                config={},
                tools=tools,
                span=span,
                tracer=tracer
            )

        assert res.has_tool_calls is False
        assert res.direct_return_state is not None
        assert res.direct_return_state["sql_validated"] is True
        assert res.direct_return_state["raw_data"] == '[{"count": 100}]'
        assert res.direct_return_state["sql_query"] == "SELECT count(*) FROM fqz_gz_jzsj_all_ql"
