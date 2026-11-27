import pytest
from unittest.mock import AsyncMock, patch
from app.skills.schema.semantic_encyclopedia_parser import SemanticEncyclopediaParser
from app.skills.schema.semantic_hyde_generator import SemanticHydeGenerator
from app.skills.schema.semantic_prompt_formatter import SemanticPromptFormatter
from app.skills.schema.semantic_layer import SemanticRetriever, semantic_retriever


def test_semantic_encyclopedia_parser_core_seeds():
    """测试百科解析器核心种子提取与字段结构"""
    parser = SemanticEncyclopediaParser(schema_file="nonexistent_schema.md")
    extracted = parser.extract_metadata()
    assert len(extracted) >= 8
    tables = {item["table"] for item in extracted}
    assert "v_audit_hospital_monthly" in tables
    assert "fqz_all_yy_yd_1" in tables
    assert all("full_text" in item and "column" in item for item in extracted)


def test_semantic_encyclopedia_parser_markdown_table(tmp_path):
    """测试 Markdown 表格解析与区域标签解析"""
    md_file = tmp_path / "mock_encyclopedia.md"
    content = """## 📂 医疗就诊域
### 1. fqz_fymx_test - 费用明细测试库
【业务价值】：就诊明细审计核查
| 物理字段 | 字段含义 | 字段类型 | 审计意义 |
| :--- | :--- | :--- | :--- |
| `det_item_fee_sumamt` | 明细总费用 [上海] | Decimal | 违规金额统计 |
| `psn_no` | 个人唯一编码 | String | 人员识别 |
"""
    md_file.write_text(content, encoding="utf-8")
    parser = SemanticEncyclopediaParser(schema_file=str(md_file))
    extracted = parser.extract_metadata()
    cols = {item["column"]: item for item in extracted if item["table"] == "fqz_fymx_test"}
    assert "det_item_fee_sumamt" in cols
    assert cols["det_item_fee_sumamt"]["region"] == "上海"
    assert "psn_no" in cols
    assert cols["psn_no"]["region"] == "GLOBAL"


@pytest.mark.asyncio
async def test_semantic_hyde_generator(monkeypatch):
    """测试 HyDE 假设性上下文生成与异常安全降级"""
    from app.core.llm_provider import llm_provider
    generator = SemanticHydeGenerator()
    mock_resp = AsyncMock()
    mock_resp.content = "假设性医保审计上下文：排查男性结算妇科专属药品的明细金额与发生频次。"
    
    monkeypatch.setattr(llm_provider, "chat", AsyncMock(return_value=mock_resp))
    res = await generator.generate_hyde_context("排查男性使用妇科药品")
    assert "男性" in res
    assert "妇科" in res

    # 异常降级
    monkeypatch.setattr(llm_provider, "chat", AsyncMock(side_effect=RuntimeError("LLM Down")))
    res_fail = await generator.generate_hyde_context("测试异常")
    assert res_fail == ""



def test_semantic_prompt_formatter():
    """测试防御性类型转换提示生成"""
    formatter = SemanticPromptFormatter()
    items = [
        {"table": "fqz_t1", "column": "medfee_sumamt", "type": "String", "desc": "医疗总费用"},
        {"table": "fqz_t1", "column": "setl_time", "type": "String", "desc": "结算时间"},
        {"table": "fqz_t1", "column": "org_name", "type": "String", "desc": "定点机构名称"},
    ]
    prompt_text = formatter.format_for_prompt(items)
    assert "| 表名 | 字段名 | 物理类型 | 语义/审计价值 | 核心编写建议 |" in prompt_text
    assert "toFloat64OrZero" in prompt_text or "toInt32OrZero" in prompt_text
    assert "toDate" in prompt_text
    assert "直接使用" in prompt_text

    # 空列表友好提示
    assert formatter.format_for_prompt([]) == "暂未检索到相关物理字段。"


def test_semantic_retriever_facade():
    """测试 SemanticRetriever 门面向后兼容性"""
    assert isinstance(semantic_retriever, SemanticRetriever)
    guide = semantic_retriever.get_avoidance_guides("测试查询")
    assert isinstance(guide, str)
