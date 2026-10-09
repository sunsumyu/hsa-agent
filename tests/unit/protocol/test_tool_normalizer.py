import pytest
from app.core.protocol.tool_normalizer import ToolResponseNormalizer, NormalizedToolCallResult

def test_normalizer_handles_cte_with_trailing_tags():
    raw = """WITH RefundDetails AS (
        SELECT setl_id, det_item_fee_sumamt FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0
    ) SELECT count() AS refund_detail_count FROM RefundDetails</DSML parameter></DSML invoke>"""
    result = ToolResponseNormalizer.normalize(raw)
    assert result.synthesized_sql is not None
    assert result.synthesized_sql.startswith("WITH RefundDetails AS")
    assert "</DSML" not in result.synthesized_sql
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "execute_audit_sql"
    assert result.tool_calls[0]["args"]["sql"] == result.synthesized_sql
    assert result.is_synthesized is True

def test_normalizer_handles_trailing_json_quotes_in_xml():
    raw = '<execute_audit_sql>SELECT count(*) FROM fqz_drug_mcs_info_list"}\n</execute_audit_sql>'
    result = ToolResponseNormalizer.normalize(raw)
    assert result.synthesized_sql == "SELECT count(*) FROM fqz_drug_mcs_info_list"
    assert result.tool_calls[0]["args"]["sql"] == "SELECT count(*) FROM fqz_drug_mcs_info_list"
    assert result.is_synthesized is True

def test_normalizer_preserves_existing_valid_tool_calls():
    calls = [{"name": "execute_audit_sql", "args": {"sql": "SELECT 1"}}]
    result = ToolResponseNormalizer.normalize("some text", existing_tool_calls=calls)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "execute_audit_sql"
    assert result.tool_calls[0]["args"]["sql"] == "SELECT 1"
    assert result.synthesized_sql == "SELECT 1"
    assert result.is_synthesized is False

def test_normalizer_cleans_dirty_sql_in_existing_tool_calls():
    # 即使存在 tool_calls，若参数内部残留 XML 或闭合标签，也应自动清洗
    calls = [{"name": "execute_audit_sql", "args": {"sql": "SELECT * FROM fqz_table\"}\n</tool>"}}]
    result = ToolResponseNormalizer.normalize("some text", existing_tool_calls=calls)
    assert result.tool_calls[0]["args"]["sql"] == "SELECT * FROM fqz_table"
    assert result.synthesized_sql == "SELECT * FROM fqz_table"
    assert result.is_synthesized is False

def test_normalizer_handles_markdown_code_blocks():
    raw = "```sql\nSELECT col FROM fqz_fymx_test\n```"
    result = ToolResponseNormalizer.normalize(raw)
    assert result.synthesized_sql == "SELECT col FROM fqz_fymx_test"
    assert len(result.tool_calls) == 1

def test_normalizer_handles_deepseek_unicode_dsml_tags():
    raw = '<｜｜DSML｜｜ parameter name="sql" string="true">SELECT toDate(setl_time) AS setl_date, count(DISTINCT setl_id) AS setl_count FROM fqz_gz_jzsj_all_ql WHERE setl_time >= \'2024-01-01\' GROUP BY setl_date</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>'
    result = ToolResponseNormalizer.normalize(raw)
    assert result.synthesized_sql == "SELECT toDate(setl_time) AS setl_date, count(DISTINCT setl_id) AS setl_count FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' GROUP BY setl_date"
    assert "DSML" not in result.synthesized_sql
    assert "</" not in result.synthesized_sql
    assert result.is_synthesized is True

def test_normalizer_preserves_trailing_string_literal_quotes():
    # 验证末尾以单引号字符串结束的 SQL 不会被误切单引号
    raw_sql = "SELECT fixmedins_code FROM fqz_all_yy_yd WHERE hosp_lv LIKE '%二级%'"
    calls = [{"name": "execute_audit_sql", "args": {"sql": raw_sql}}]
    result = ToolResponseNormalizer.normalize("some text", existing_tool_calls=calls)
    assert result.tool_calls[0]["args"]["sql"] == raw_sql
    assert result.synthesized_sql == raw_sql

    raw_sql_2 = "SELECT count() FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' AND setl_time < '2025-01-01'"
    result_2 = ToolResponseNormalizer.clean_sql_ast(raw_sql_2)
    assert result_2 == raw_sql_2

def test_normalizer_aliases_hallucinated_tool_names():
    """验证模型幻觉工具调用名（如复数 write_audit_notes）被自动归一化为正确工具名"""
    calls = [
        {"name": "write_audit_notes", "args": {"category": "risk", "content": "finding"}},
        {"name": "read_audit_note", "args": {}},
    ]
    result = ToolResponseNormalizer.normalize("some text", existing_tool_calls=calls)
    assert result.tool_calls[0]["name"] == "write_audit_note"
    assert result.tool_calls[1]["name"] == "read_all_audit_notes"

def test_normalizer_rejects_conversational_text_with_sql_keywords():
    """验证包含 SELECT / FROM 关键字的自然语言解释绝不会被误合成工具调用"""
    conversational = (
        "## 审计执行状态：受阻，本轮未产出可采信结论\n\n"
        "1. 我先后提交了结构探查等 SELECT 语句。\n"
        "2. 工具全部返回 status: ERROR。从 fqz_all_yy_yd 读取的结构不一致。\n"
        "判定：工具层当前不可用，其返回不具备证据资格。"
    )
    result = ToolResponseNormalizer.normalize(conversational)
    assert len(result.tool_calls) == 0
    assert result.synthesized_sql is None
    assert result.is_synthesized is False

def test_normalizer_handles_dsml_schema_lookup():
    raw = '''明白，我先同步真实物理蓝图，确认 `fqz_fymx_test` 及主表的真实字段。
<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="lookup_medical_schema">
<｜｜DSML｜｜ parameter name="table_name" string="true">fqz_fymx_test</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>'''
    result = ToolResponseNormalizer.normalize(raw)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "lookup_medical_schema"
    assert result.tool_calls[0]["args"] == {"table_name": "fqz_fymx_test"}
    assert result.is_synthesized is True

def test_normalizer_handles_dsml_execute_audit_sql_invoke():
    raw = '''<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="execute_audit_sql">
<｜｜DSML｜｜ parameter name="sql" string="true">SELECT count() FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>'''
    result = ToolResponseNormalizer.normalize(raw)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "execute_audit_sql"
    assert result.tool_calls[0]["args"]["sql"] == "SELECT count() FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0"
    assert result.synthesized_sql == "SELECT count() FROM fqz_fymx_test WHERE det_item_fee_sumamt < 0"
    assert result.is_synthesized is True


