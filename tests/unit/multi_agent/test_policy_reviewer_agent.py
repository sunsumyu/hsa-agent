import pytest
from langchain_core.messages import AIMessage

from app.multi_agent.contracts import SQLAuditArtifact
from app.multi_agent.policy_reviewer_agent import PolicyReviewerSubagent


@pytest.mark.asyncio
async def test_policy_reviewer_strips_upstream_sql_cot_and_cites_statutes():
    captured_msgs = []

    async def fake_llm(role, messages, **kwargs):
        captured_msgs.extend(messages)
        return AIMessage(
            content=(
                "【临床豁免复核】：需核查是否存在晚期前列腺肿瘤内分泌治疗等合规适应症，对无肿瘤诊断记录者定性违规。\n"
                "【风险等级】：高"
            )
        )

    sql_art = SQLAuditArtifact(
        subtask_id="s1",
        focus_title="性别用药冲突",
        sql_query="SELECT SECRET_INTERNAL_COT_MARKER FROM fqz_fymx_test",
        raw_data='[{"hilist_name": "戊酸雌二醇片", "cnt": 473}]',
        row_count=473,
        total_amount=15899.70,
        validated=True,
    )

    reviewer = PolicyReviewerSubagent(llm_caller=fake_llm)
    verdict = await reviewer.review(
        user_query="核查男性开具妇科药并剔除临床合理适应症",
        sql_artifacts=[sql_art],
    )

    prompt_blob = "\n".join(str(m.content) for m in captured_msgs)
    assert "SECRET_INTERNAL_COT_MARKER" not in prompt_blob
    assert "473" in prompt_blob
    assert verdict.risk_level == "高"
    assert len(verdict.statutory_citations) >= 1
    assert "前列腺" in verdict.exemption_notes


@pytest.mark.asyncio
async def test_policy_reviewer_splits_semicolon_citations_and_handles_empty_match(monkeypatch):
    async def fake_llm(role, messages, **kwargs):
        return AIMessage(content="【临床豁免复核】：未见明显异常。\n【风险等级】：低")

    sql_art = SQLAuditArtifact(
        subtask_id="s2",
        focus_title="常规核查",
        sql_query="SELECT 1",
        raw_data="[]",
        row_count=0,
        total_amount=0.0,
        validated=True,
    )

    monkeypatch.setattr(
        "app.multi_agent.policy_reviewer_agent.match_policies",
        lambda q: "法规条款A；法规条款B",
    )
    reviewer = PolicyReviewerSubagent(llm_caller=fake_llm)
    verdict = await reviewer.review(user_query="常规核查", sql_artifacts=[sql_art])
    assert verdict.statutory_citations == ["法规条款A", "法规条款B"]
    assert verdict.risk_level == "低"

    monkeypatch.setattr(
        "app.multi_agent.policy_reviewer_agent.match_policies",
        lambda q: "",
    )
    empty_verdict = await reviewer.review(user_query="常规核查", sql_artifacts=[sql_art])
    assert empty_verdict.statutory_citations == []


@pytest.mark.asyncio
async def test_policy_reviewer_degrades_gracefully_on_llm_error():
    async def failing_llm(role, messages, **kwargs):
        raise RuntimeError("LLM timeout")

    sql_art = SQLAuditArtifact(
        subtask_id="s3",
        focus_title="大额异常",
        sql_query="SELECT 1",
        raw_data='[{"amt": 5000}]',
        row_count=10,
        total_amount=5000.0,
        validated=True,
    )

    reviewer = PolicyReviewerSubagent(llm_caller=failing_llm)
    verdict = await reviewer.review(user_query="大额结算异常核查", sql_artifacts=[sql_art])
    assert verdict.risk_level == "高"
    assert len(verdict.statutory_citations) >= 1
    assert "复核" in verdict.exemption_notes


@pytest.mark.asyncio
async def test_policy_reviewer_executes_tool_calls_and_synthesizes_review(monkeypatch):
    call_records = []
    tool_invocations = []

    class FakeTool:
        name = "query_law_database"

        async def ainvoke(self, args):
            tool_invocations.append(args)
            return "《医疗保障基金使用监督管理条例》第十五条"

    monkeypatch.setattr(
        "app.multi_agent.policy_reviewer_agent._REVIEW_TOOLS",
        [FakeTool()],
    )

    async def fake_llm(role, messages, allow_tools=True, **kwargs):
        call_records.append((allow_tools, len(messages)))
        if len(call_records) == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "tc-1", "name": "query_law_database", "args": {"query": "重复收费"}}],
            )
        return AIMessage(content="【临床豁免复核】：已核对法规库，确认存在重复收费违规。\n【风险等级】：高")

    sql_art = SQLAuditArtifact(
        subtask_id="s4",
        focus_title="重复收费核查",
        sql_query="SELECT 1",
        raw_data='[{"cnt": 12}]',
        row_count=12,
        total_amount=3600.0,
        validated=True,
    )

    reviewer = PolicyReviewerSubagent(llm_caller=fake_llm)
    verdict = await reviewer.review(user_query="重复收费核查", sql_artifacts=[sql_art])

    assert tool_invocations == [{"query": "重复收费"}]
    assert call_records == [(True, 2), (False, 4)]
    assert "重复收费违规" in verdict.exemption_notes
    assert verdict.risk_level == "高"


@pytest.mark.asyncio
async def test_policy_reviewer_falls_back_to_static_when_llm_returns_empty_content():
    async def empty_llm(role, messages, **kwargs):
        return AIMessage(content="   ")

    sql_art = SQLAuditArtifact(
        subtask_id="s5",
        focus_title="空回复兜底",
        sql_query="SELECT 1",
        raw_data="[]",
        row_count=0,
        total_amount=0.0,
        validated=True,
    )

    reviewer = PolicyReviewerSubagent(llm_caller=empty_llm)
    verdict = await reviewer.review(user_query="常规核查", sql_artifacts=[sql_art])

    assert verdict.exemption_notes != ""
    assert "复核" in verdict.exemption_notes
