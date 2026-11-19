import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.core.context.turn_history_compactor import compact_past_turns, compress_messages_by_budget


def test_compact_past_turns_single_turn_unchanged():
    msgs = [
        HumanMessage(content="查询涉案金额第一的医院"),
        AIMessage(content="涉案第一的是第一人民医院，金额5000元")
    ]
    res = compact_past_turns(msgs)
    assert len(res) == 2
    assert res[0].content == msgs[0].content
    assert res[1].content == msgs[1].content


def test_compact_past_turns_prunes_intermediate_tool_calls_in_past_turns():
    long_report = (
        "### 审计结论\n第1轮核查完成，发现违规金额 10000 元。\n### 证据链\n"
        + "详细明细" * 100
    )
    msgs = [
        HumanMessage(content="第1轮提问"),
        AIMessage(content="", tool_calls=[{"name": "sql_query", "args": {"sql": "SELECT 1"}, "id": "tc1"}]),
        ToolMessage(content="[1]", tool_call_id="tc1"),
        AIMessage(content=long_report),
        HumanMessage(content="第2轮提问（当前轮次活跃提问）"),
        AIMessage(content="", tool_calls=[{"name": "sql_query", "args": {"sql": "SELECT 2"}, "id": "tc2"}])
    ]
    res = compact_past_turns(msgs)
    
    # 期望：第1轮中的中间纯 tool_calls AIMessage 被过滤，第1轮结论被高保真瘦身，第2轮（活跃轮次）完全保留
    res_contents = [getattr(m, "content", "") for m in res]
    assert any("第1轮核查完成" in c for c in res_contents)
    assert any("前序底稿已归档" in c for c in res_contents)
    # 当前活跃轮次的 tool_calls 必须完整保留
    last_msg = res[-1]
    assert hasattr(last_msg, "tool_calls") and len(last_msg.tool_calls) == 1


def test_compress_messages_by_budget_generates_deterministic_summary():
    system_msg = SystemMessage(content="System prompt")
    gssc_msg = SystemMessage(content="【当前审计黄金上下文载荷 (GSSC 动态精选渲染版)】：<schemas></schemas>")
    
    chat_msgs = []
    # 构造大量历史消息使 token 远超 500
    for i in range(20):
        chat_msgs.append(HumanMessage(content=f"历史问题 {i}: 涉案医疗机构违规费用 SELECT * FROM fqz_fymx_test WHERE id = {i}"))
        chat_msgs.append(AIMessage(content=f"历史回答 {i}: 涉案金额 8888.88 元，存在违规开药行为。"))
        
    all_msgs = [system_msg, gssc_msg] + chat_msgs
    compressed = compress_messages_by_budget(all_msgs, max_tokens=600)
    
    # 应该包含确定性摘要块
    summary_msg = next((m for m in compressed if "历史事实高保真确定性摘要" in str(getattr(m, "content", ""))), None)
    assert summary_msg is not None
    assert "fqz_fymx_test" in summary_msg.content
