import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.llm_provider import LLMProvider


def test_resolve_tier_id():
    """测试逻辑层级到物理模型 ID 的映射"""
    provider = LLMProvider()
    with patch.dict("os.environ", {"HEAVY_MODEL": "custom-heavy", "LIGHT_MODEL": "custom-light"}):
        assert provider._resolve_tier_id("HEAVY") == "custom-heavy"
        assert provider._resolve_tier_id("LIGHT") == "custom-light"


def test_extract_last_user_message():
    """测试从复杂对话历史中提取最后一条用户提问"""
    provider = LLMProvider()
    messages = [
        SystemMessage(content="系统提示"),
        HumanMessage(content="第一个问题"),
        AIMessage(content="第一个回答"),
        ("human", "第二个问题（tuple格式）"),
        AIMessage(content="第二个回答"),
    ]
    extracted = provider._extract_last_user_message(messages)
    assert extracted == "第二个问题（tuple格式）"


@pytest.mark.asyncio
async def test_enrich_context_skipped_for_light_roles():
    """测试非 planner/coder 角色不会执行沉重的上下文增强流水线"""
    provider = LLMProvider()
    messages = [HumanMessage(content="统计违规总金额")]
    state = {"current_turn_query": "统计违规总金额", "metadata": {}}
    
    # 针对 reporter 角色，直接原样返回历史
    enriched = await provider._enrich_context_if_needed("reporter", messages, state)
    assert enriched == messages


@pytest.mark.asyncio
async def test_execute_model_call_non_streaming():
    """测试 _execute_model_call 在普通调用分支下的正确执行与解包"""
    provider = LLMProvider()
    mock_llm = MagicMock()
    mock_llm.streaming = False
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="[LLM响应] 审计完成"))
    
    messages = [HumanMessage(content="你好")]
    obs_config = {}
    
    response = await provider._execute_model_call(mock_llm, messages, obs_config)
    assert response.content == "[LLM响应] 审计完成"
    mock_llm.ainvoke.assert_awaited_once_with(messages, config=obs_config)


@pytest.mark.asyncio
async def test_execute_model_call_streaming():
    """测试 _execute_model_call 在流式调用分支下的累加拼合"""
    provider = LLMProvider()
    mock_llm = MagicMock()
    mock_llm.streaming = True
    
    async def fake_astream(msgs, config=None):
        yield AIMessage(content="第一段")
        yield AIMessage(content="第二段")
    
    mock_llm.astream = fake_astream
    messages = [HumanMessage(content="你好")]
    obs_config = {}
    
    response = await provider._execute_model_call(mock_llm, messages, obs_config)
    assert response.content == "第一段第二段"
