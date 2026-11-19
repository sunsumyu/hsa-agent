"""
tests/unit/reporting/test_conclusion_orchestrator_red.py
=========================================================
[SPEC-227 / Matt Pocock Deep Module] 审计结论仲裁与自适应直通解耦测试 (红灯先行)
"""

import pytest
from langchain_core.messages import AIMessage
from app.reporting.conclusion_orchestrator import resolve_conclusion


@pytest.mark.asyncio
async def test_resolve_conclusion_fast_route():
    """测试快速路由直通分支：无需调用 LLM，基于确定性模板秒级生成结论"""
    state = {
        "metadata": {
            "fast_route_id": "RULE_001",
            "user_question": "排查门诊特殊病超量开药",
        },
        "sql_query": "SELECT * FROM fqz_fymx_test",
    }
    raw_data = [
        {"psn_no": "P001", "det_item_fee_sumamt": 500.0, "hospital": "测试三甲医院", "item_name": "阿莫西林胶囊"}
    ]
    conclusion, is_restricted = await resolve_conclusion(
        state=state,
        raw_data_list=raw_data,
        hard_count=1,
        hard_sum=500.0,
    )
    assert not is_restricted
    assert "测试三甲医院" in conclusion or "P001" in conclusion or "阿莫西林胶囊" in conclusion or "500" in conclusion


@pytest.mark.asyncio
async def test_resolve_conclusion_coder_summary_reuse():
    """测试 Coder 结论复用分支：当 Coder 已输出高质量核查指标时，直接复用，杜绝二次 LLM 延迟"""
    coder_text = (
        "## 审计指标总结\n"
        "本次排查共覆盖 120 笔单据，检出违规记录 3 条，涉及金额 ¥12,500.00。"
        "主要表现为多频次重复结算与限定性别开药。"
    )
    state = {
        "metadata": {"user_question": "核查男性妇科用药"},
        "sql_query": "SELECT * FROM fqz_fymx_test WHERE gend = '1'",
        "messages": [AIMessage(content=coder_text)],
    }
    raw_data = [{"psn_no": "P01", "fee": 100.0}]
    conclusion, is_restricted = await resolve_conclusion(
        state=state,
        raw_data_list=raw_data,
        hard_count=3,
        hard_sum=12500.0,
    )
    assert not is_restricted
    assert conclusion == coder_text


@pytest.mark.asyncio
async def test_resolve_conclusion_zero_finding_baseline():
    """测试零违规基线直通：检出为 0 且证据有效时，使用客观合规模板"""
    state = {
        "metadata": {"user_question": "全量排查某医院过度检查"},
        "sql_query": "SELECT * FROM fqz_fymx_test WHERE ...",
        "sql_validated": True,
        "messages": [AIMessage(content="查询完成")],
    }
    raw_data = []  # 检出为 0
    conclusion, is_restricted = await resolve_conclusion(
        state=state,
        raw_data_list=raw_data,
        hard_count=0,
        hard_sum=0.0,
    )
    assert not is_restricted
    assert "未发现任何违规异常单据" in conclusion
    assert "¥0.00" in conclusion


@pytest.mark.asyncio
async def test_resolve_conclusion_restricted_fallback():
    """测试逃生舱/受限模式：重试耗尽且无有效证据时，标记 is_restricted 为 True 并返回合规告知"""
    state = {
        "metadata": {"user_question": "排查复杂欺诈环"},
        "retry_count": 5,
        "error_log": "REACHED_MAX_RETRIES: 尝试多次仍失败",
        "sql_validated": False,
        "messages": [],
    }
    conclusion, is_restricted = await resolve_conclusion(
        state=state,
        raw_data_list=[],
        hard_count=0,
        hard_sum=0.0,
        max_retries=1,
    )
    assert is_restricted is True
    assert "受限" in conclusion or "未产出确切违规结论" in conclusion or "记录" in conclusion
