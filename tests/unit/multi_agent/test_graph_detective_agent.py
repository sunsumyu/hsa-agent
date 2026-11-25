import pytest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
from app.multi_agent.graph_detective_agent import GraphDetectiveSubagent


@pytest.mark.asyncio
async def test_graph_detective_prompt_strictly_excludes_relational_tables():
    captured_messages = []

    async def fake_llm(role, messages, **kwargs):
        captured_messages.extend(messages)
        return AIMessage(
            content="",
            tool_calls=[{
                "id": "tc_1",
                "name": "federated_graph_sideloader",
                "args": {
                    "cypher": "MATCH (p1:Patient)-[:HAS_PHONE]->(t:Phone)<-[:HAS_PHONE]-(p2:Patient) WHERE p1.psn_no <> p2.psn_no RETURN DISTINCT p1.psn_no AS id",
                    "return_key": "id",
                },
            }],
        )

    fake_sideloader = AsyncMock(return_value={
        "status": "SIDELOADED",
        "temp_table": "fqz_temp_sl_99887766",
        "message": "侧载成功！在 Neo4j 中发现了 6 个目标实体。",
    })

    agent = GraphDetectiveSubagent(llm_caller=fake_llm, sideload_fn=fake_sideloader)
    artifact = await agent.investigate("排查共用手机号团伙骗保")

    prompt_blob = "\n".join(str(m.content) for m in captured_messages)
    assert "Patient" in prompt_blob and "HAS_PHONE" in prompt_blob
    assert "fqz_fymx_test" not in prompt_blob
    assert "fqz_gz_jzsj_all_ql" not in prompt_blob
    assert artifact.succeeded is True
    assert artifact.temp_table == "fqz_temp_sl_99887766"


@pytest.mark.asyncio
async def test_graph_detective_gracefully_degrades_when_neo4j_offline():
    async def fake_llm(role, messages, **kwargs):
        return AIMessage(
            content="",
            tool_calls=[{
                "id": "tc_1",
                "name": "federated_graph_sideloader",
                "args": {"cypher": "MATCH (p:Patient) RETURN p.psn_no AS id", "return_key": "id"},
            }],
        )

    fake_sideloader = AsyncMock(return_value={
        "status": "ERROR",
        "error_message": "联邦侧载失败: Neo4j 服务未连接",
    })

    agent = GraphDetectiveSubagent(llm_caller=fake_llm, sideload_fn=fake_sideloader)
    artifact = await agent.investigate("排查共用手机号团伙骗保")

    assert artifact.succeeded is False
    assert artifact.degraded_to_relational is True
    assert artifact.temp_table is None


def test_graph_only_tools_schema_has_no_fqz_leak():
    import json
    from app.multi_agent.graph_detective_agent import build_graph_only_tools

    for tool in build_graph_only_tools():
        blob = json.dumps(
            [tool.name, tool.description, tool.get_input_jsonschema()], ensure_ascii=False
        )
        assert "fqz_" not in blob


@pytest.mark.asyncio
async def test_bound_tools_passed_to_llm_are_fqz_free():
    from app.multi_agent import graph_detective_agent as mod

    agent = GraphDetectiveSubagent(sideload_fn=AsyncMock(return_value={"status": "ERROR", "error_message": "x"}))
    blob = "\n".join(f"{t.name} {t.description} {t.get_input_jsonschema()}" for t in agent._tools)
    assert "fqz_" not in blob
    assert mod.build_graph_only_tools()


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [
    "联邦侧载失败: Neo.ClientError.Statement.SyntaxError: Invalid input",
    "侧载到 ClickHouse 失败: table write error",
])
async def test_non_connectivity_failures_do_not_degrade(err):
    async def fake_llm(role, messages, **kwargs):
        return AIMessage(content="", tool_calls=[])

    agent = GraphDetectiveSubagent(
        llm_caller=fake_llm,
        sideload_fn=AsyncMock(return_value={"status": "ERROR", "error_message": err}),
    )
    artifact = await agent.investigate("q")
    assert artifact.succeeded is False
    assert artifact.degraded_to_relational is False


@pytest.mark.asyncio
async def test_sideload_exception_returns_degraded_artifact():
    async def fake_llm(role, messages, **kwargs):
        return AIMessage(content="", tool_calls=[])

    agent = GraphDetectiveSubagent(
        llm_caller=fake_llm, sideload_fn=AsyncMock(side_effect=RuntimeError("boom"))
    )
    artifact = await agent.investigate("q")
    assert artifact.succeeded is False
    assert artifact.degraded_to_relational is True
    assert artifact.temp_table is None
    assert "boom" in artifact.summary
