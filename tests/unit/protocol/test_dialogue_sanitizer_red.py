import pytest
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from app.core.protocol.dialogue_sanitizer import (
    sanitize_dialogue_protocol,
    unpack_response_content,
)


def test_merge_scattered_system_messages():
    """测试多条分散的 SystemMessage 归一化合并为单一头部 SystemMessage"""
    messages = [
        SystemMessage(content="系统指令1：遵守医保反欺诈规范。"),
        HumanMessage(content="你好"),
        SystemMessage(content="系统指令2：严禁编造虚假数据。"),
        AIMessage(content="您好，请提供需要审计的医院编码。"),
    ]
    sanitized = sanitize_dialogue_protocol(messages)
    
    # 头部应该只有 1 条 SystemMessage
    assert isinstance(sanitized[0], SystemMessage)
    assert "系统指令1" in sanitized[0].content
    assert "系统指令2" in sanitized[0].content
    assert "\n\n---\n\n" in sanitized[0].content
    
    # 后续不能再有 SystemMessage
    sys_count = sum(1 for m in sanitized if isinstance(m, SystemMessage))
    assert sys_count == 1
    
    # 剩下的非 system 消息顺序正常
    assert any(isinstance(m, HumanMessage) and m.content == "你好" for m in sanitized)


def test_system_message_cache_control_flag():
    """测试系统消息长内容自动打上 cache_control 标记"""
    long_content = "医保知识库指令：" + "A" * 1050
    messages = [
        SystemMessage(content=long_content),
        HumanMessage(content="查一下某某"),
    ]
    sanitized = sanitize_dialogue_protocol(messages)
    assert sanitized[0].additional_kwargs.get("cache_control") == {"type": "ephemeral"}


def test_collapse_consecutive_same_role_dialogue():
    """测试合并连续同角色消息，确保满足 user/assistant 交替"""
    messages = [
        HumanMessage(content="第一句话"),
        HumanMessage(content="第二句话补充说明"),
        AIMessage(content="回答分段一"),
        AIMessage(content="回答分段二"),
    ]
    sanitized = sanitize_dialogue_protocol(messages)
    
    # 连续 HumanMessage 合并为 1 条
    human_msgs = [m for m in sanitized if isinstance(m, HumanMessage)]
    assert len(human_msgs) == 1
    assert "第一句话" in human_msgs[0].content
    assert "第二句话补充说明" in human_msgs[0].content

    # 连续 AIMessage 合并为 1 条
    ai_msgs = [m for m in sanitized if isinstance(m, AIMessage)]
    assert len(ai_msgs) == 1
    assert "回答分段一" in ai_msgs[0].content
    assert "回答分段二" in ai_msgs[0].content


def test_preserve_ai_message_with_tool_calls():
    """测试带有 tool_calls 的 AIMessage 不会被盲目合并"""
    tool_ai = AIMessage(
        content="我来查询 ClickHouse",
        tool_calls=[{"name": "execute_query", "args": {"sql": "SELECT 1"}, "id": "call_1"}]
    )
    tool_msg = ToolMessage(content="[1]", tool_call_id="call_1")
    next_ai = AIMessage(content="查询完成")

    messages = [
        HumanMessage(content="查一下"),
        tool_ai,
        tool_msg,
        next_ai,
    ]
    sanitized = sanitize_dialogue_protocol(messages)
    # tool_ai 和 tool_msg 应该完整保留配对
    assert len(sanitized) == 4
    assert sanitized[1].tool_calls == tool_ai.tool_calls


def test_fallback_human_message_when_no_user_message():
    """测试当全为 SystemMessage 时，自动追加保底 HumanMessage 防止 API 拒绝"""
    messages = [
        SystemMessage(content="你是反欺诈审计 Agent。")
    ]
    sanitized = sanitize_dialogue_protocol(messages)
    assert len(sanitized) == 2
    assert isinstance(sanitized[0], SystemMessage)
    assert isinstance(sanitized[1], HumanMessage)
    assert "审计分析" in sanitized[1].content


def test_unpack_response_content():
    """测试 Claude/Thinking Content Block 解包为纯文本字符串"""
    # 场景 1：纯文本字符串
    assert unpack_response_content("正常文本") == "正常文本"
    
    # 场景 2：字符串列表
    assert unpack_response_content(["段落1", "段落2"]) == "段落1\n段落2"
    
    # 场景 3：字典块列表（Claude text blocks）
    blocks = [
        {"type": "thinking", "thinking": "Let me think..."},
        {"type": "text", "text": "这是输出结果1"},
        {"type": "text", "text": "这是输出结果2"},
    ]
    assert unpack_response_content(blocks) == "这是输出结果1\n这是输出结果2"
