import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.agents.reflection_diagnostic_policy import ReflectionDiagnosticPolicy
from app.agents.reflection_prompt_assembler import ReflectionPromptAssembler
from app.agents.reflection_agent import AuditReflectionAgent


def test_diagnostic_policy_escape_hatch_threshold():
    policy = ReflectionDiagnosticPolicy(max_retries=3)
    assert not policy.is_escape_hatch_triggered(retry_count=0)
    assert not policy.is_escape_hatch_triggered(retry_count=1)
    assert policy.is_escape_hatch_triggered(retry_count=2)
    assert policy.is_escape_hatch_triggered(retry_count=3)

    escape_msg = policy.generate_escape_hatch_message()
    assert isinstance(escape_msg, AIMessage)
    assert "已进入降级报告模式" in escape_msg.content
    assert "受限核查报告" in escape_msg.content


def test_reflection_prompt_assembler_truncation_and_context():
    assembler = ReflectionPromptAssembler()
    long_raw_data = "x" * 2000
    state = {
        "current_turn_query": "查询男性妇科用药",
        "methodology": "性别互斥算法",
        "raw_data": long_raw_data,
        "error_log": "Table 'fqz_fymx' does not exist",
        "messages": [
            HumanMessage(content="历史消息 1"),
            AIMessage(content="历史消息 2"),
            HumanMessage(content="历史消息 3 (最近)"),
            AIMessage(content="历史消息 4 (最近)"),
        ],
    }

    assembled_messages = assembler.assemble_critic_messages(state)
    assert len(assembled_messages) > 0
    # 验证提取的 prompt 中包含了截断后的数据
    formatted_str = "".join(str(m.content) for m in assembled_messages)
    assert "查询男性妇科用药" in formatted_str
    # 1000 长度截断校验
    assert "x" * 1000 in formatted_str
    assert "x" * 1001 not in formatted_str


@pytest.mark.asyncio
async def test_audit_reflection_agent_reflect_normal_flow():
    agent = AuditReflectionAgent(max_retries=3)
    state = {
        "retry_count": 0,
        "current_turn_query": "查询违规大额结算",
        "methodology": "阈值排查",
        "raw_data": "[]",
        "error_log": "SQL syntax error near 'WHER'",
        "messages": [HumanMessage(content="查询违规大额结算")],
    }

    mock_response = AIMessage(content="SQL 中拼写错误，请将 WHER 修改为 WHERE。")
    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        result = await agent.reflect(state, config={})

        assert result["retry_count"] == 1
        assert "[CRITIC 反馈]" in result["error_log"]
        assert "WHERE" in result["error_log"]
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == mock_response.content
        mock_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_reflection_agent_reflect_escape_hatch_flow():
    agent = AuditReflectionAgent(max_retries=3)
    state = {
        "retry_count": 2,  # 已经尝试了 2 次，达到 max_retries - 1
        "current_turn_query": "查询违规大额结算",
        "methodology": "阈值排查",
        "raw_data": "[]",
        "error_log": "连续报错",
        "messages": [],
    }

    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock) as mock_chat:
        result = await agent.reflect(state, config={})

        # 逃生舱激活，不应该触发 LLM 网络调用
        mock_chat.assert_not_called()
        assert result["retry_count"] == 3
        assert "降级报告模式" in result["error_log"]
        assert "受限核查报告" in result["messages"][0].content
