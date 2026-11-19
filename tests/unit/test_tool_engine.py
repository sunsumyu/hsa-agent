"""
tests/unit/test_tool_engine.py
==============================
[V200.0] ToolEngine 深度模块接缝单元测试。

验证原则 (codebase-design):
- 接口即测试表面：测试通过 ToolEngine.execute 跨越接缝。
- 使用 FakeDbAdapter 消除外部物理数据库与网络依赖，做到完全密封 (Hermetic) 与瞬时执行。
- 验证双适配器：OpenAIToolAdapter 与 MCPToolAdapter 契约生成。
"""

import pytest
import asyncio
from app.core.tool_engine import (
    ToolEngine,
    FakeDbAdapter,
    SchemaGrounder,
    ToolCallRequest,
)


@pytest.fixture
def fake_db():
    fake = FakeDbAdapter()
    fake.set_table_data("fqz_admdvs", [
        {"admdvs": "110000", "admdvs_name": "北京市", "admdvs_lv": "1"},
        {"admdvs": "310000", "admdvs_name": "上海市", "admdvs_lv": "1"},
    ])
    fake.set_table_data("fqz_all_yy_yd", [
        {"fixmedins_name": "第一人民医院", "medins_type": "1"},
    ])
    return fake


@pytest.fixture
def engine(fake_db):
    return ToolEngine(db_adapter=fake_db)


@pytest.mark.asyncio
async def test_input_validation_rejects_empty_sql(engine):
    """验证入参校验：空 SQL 直接拦截并返回结构化 VALIDATION_ERROR"""
    res = await engine.execute({
        "name": "execute_audit_sql",
        "args": {"sql": "   "}
    })
    assert res.is_success is False
    assert res.error_type == "VALIDATION_ERROR"
    assert len(res.structured_hints) > 0


@pytest.mark.asyncio
async def test_input_validation_rejects_ddl(engine):
    """验证只读原则拦截：禁止 DROP/DELETE 等危险 DDL/DML"""
    res = await engine.execute({
        "name": "execute_audit_sql",
        "args": {"sql": "DROP TABLE fqz_admdvs"}
    })
    assert res.is_success is False
    assert res.error_type == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_schema_grounder_rewrites_alias_to_physical_table(engine, fake_db):
    """验证模式地面化：dim_std_admdvs 自动在 AST 重写为物理真实表 fqz_admdvs"""
    res = await engine.execute({
        "name": "execute_audit_sql",
        "args": {"sql": "SELECT admdvs, admdvs_name FROM dim_std_admdvs WHERE admdvs_lv = '1'"}
    })
    assert res.is_success is True
    assert res.record_count == 2
    assert "fqz_admdvs" in res.sql_executed.lower()
    assert "dim_std_admdvs" not in res.sql_executed.lower()
    assert len(res.evidence_fingerprint) == 64  # sha256 指纹


@pytest.mark.asyncio
async def test_schema_grounder_chinese_alias_rewriting(engine, fake_db):
    """验证中文业务表名自动地面化：医药机构名录 自动映射为 fqz_all_yy_yd"""
    res = await engine.execute({
        "name": "execute_audit_sql",
        "args": {"sql": "SELECT medins_name FROM 医药机构名录"}
    })
    assert res.is_success is True
    assert res.record_count == 1
    assert "fqz_all_yy_yd" in res.sql_executed.lower()


@pytest.mark.asyncio
async def test_security_violation_returns_structured_hints(engine):
    """验证安全拦截返回结构化提示，引导反思模型自愈"""
    res = await engine.execute({
        "name": "execute_audit_sql",
        "args": {"sql": "SELECT * FROM completely_fake_table"}
    })
    assert res.is_success is False
    assert res.error_type == "SECURITY_VIOLATION"
    assert any("可用底层物理主表清单" in hint for hint in res.structured_hints)


@pytest.mark.asyncio
async def test_submit_audit_plan_structured_output(engine):
    """验证 Planner 的结构化规划契约：替代脆弱的正则拆分"""
    res = await engine.execute({
        "name": "submit_audit_plan",
        "args": {
            "methodology": "先核查区划层级，再统计各层级分布",
            "tasks": [
                "查询 fqz_admdvs 表确认区划数据",
                "按 admdvs_lv 执行分组计数"
            ],
            "target_tables": ["fqz_admdvs"]
        }
    })
    assert res.is_success is True
    assert res.record_count == 2
    assert res.data["tasks"] == [
        "查询 fqz_admdvs 表确认区划数据",
        "按 admdvs_lv 执行分组计数"
    ]
    assert res.data["target_tables"] == ["fqz_admdvs"]


def test_dual_protocol_adapters_generation(engine):
    """验证双协议适配器规范生成 (OpenAI Function Calling 与 Anthropic MCP)"""
    openai_defs = engine.get_definitions(dialect="openai")
    assert len(openai_defs) >= 4
    for d in openai_defs:
        assert d["type"] == "function"
        assert "parameters" in d["function"]
        assert "properties" in d["function"]["parameters"]

    mcp_defs = engine.get_definitions(dialect="mcp")
    assert len(mcp_defs) >= 4
    for d in mcp_defs:
        assert "inputSchema" in d
        assert "properties" in d["inputSchema"]
