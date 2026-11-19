"""
tests/unit/core/test_funnel_deep_modules_red.py
================================================
红灯测试：语义白盒漏斗解耦与深模块治理
验证 IntentRewriter, MedicalAligner, HierarchySideload, BaselineBuilder
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.context.funnel import SemanticFunnel, semantic_funnel
from app.core.context.funnel_baseline_builder import build_statistical_baseline
from app.core.context.funnel_intent_rewriter import FunnelIntentRewriter, extract_json_payload


def test_extract_json_payload_with_think_and_markdown():
    """测试剥离 <think> 思考链与 Markdown JSON 代码块"""
    raw_llm_text = """<think>
    Thinking about hospital levels and financial metrics...
    </think>
    ```json
    {
        "rewritten_question": "核查二级医院门诊费用异常",
        "hospital_levels": ["二级医院"],
        "disease_keywords": ["高血压"],
        "financial_metric": "medfee_sumamt",
        "statistical_strategy": "DYNAMIC_QUANTILE_99"
    }
    ```"""
    payload = extract_json_payload(raw_llm_text)
    assert payload is not None
    assert payload["rewritten_question"] == "核查二级医院门诊费用异常"
    assert payload["hospital_levels"] == ["二级医院"]
    assert payload["statistical_strategy"] == "DYNAMIC_QUANTILE_99"


@pytest.mark.asyncio
async def test_funnel_intent_rewriter_fallback():
    """测试 LLM 异常时的降级实体重写规则"""
    rewriter = FunnelIntentRewriter()
    with patch("app.core.llm_provider.LLMProvider.chat", new_callable=AsyncMock, side_effect=RuntimeError("LLM Down")):
        result = await rewriter.rewrite_intent("核查社区诊所感冒就诊大额开药")
        assert result is not None
        assert result["rewritten_question"] == "核查社区诊所感冒就诊大额开药"
        assert "社区诊所" in result["hospital_levels"]
        assert "感冒" in result["disease_keywords"]
        assert result["financial_metric"] == "medfee_sumamt"
        assert result["statistical_strategy"] == "DYNAMIC_QUANTILE_95"


def test_funnel_baseline_builder_resilient_dashes():
    """测试双阶段基线构建器处理复杂疾病编码与多横杠自愈"""
    rewritten = {
        "statistical_strategy": "DYNAMIC_QUANTILE_99",
        "financial_metric": "fund_pay_sumamt"
    }
    # 模拟包含正常单码与异常多横杠编码 (如 J00-J02-J05)
    aligned_codes = ["Z49", "J00-J02-J05"]
    temp_table = "fqz_temp_sl_123456"

    baseline = build_statistical_baseline(rewritten, aligned_codes, temp_table)
    assert baseline["strategy"] == "DYNAMIC_QUANTILE_99"
    assert baseline["metric"] == "fund_pay_sumamt"
    assert baseline["quantile"] == 0.99
    
    sql = baseline["phase1_baseline_sql"]
    assert "quantile(0.99)(fund_pay_sumamt)" in sql
    assert "INNER JOIN fqz_temp_sl_123456 AS temp_inst" in sql
    assert "dise_code LIKE 'Z49%'" in sql
    assert "dise_code >= 'J00' AND dise_code <= 'J05'" in sql


def test_funnel_baseline_builder_none_strategy():
    """测试策略为 NONE 时返回空字典"""
    baseline = build_statistical_baseline({"statistical_strategy": "NONE"}, [], None)
    assert baseline == {}


def test_semantic_funnel_facade_compatibility():
    """测试 SemanticFunnel 单例向后兼容与方法接口完整性"""
    assert hasattr(semantic_funnel, "rewrite_intent")
    assert hasattr(semantic_funnel, "align_medical_codes")
    assert hasattr(semantic_funnel, "sideload_hospital_hierarchy")
    assert hasattr(semantic_funnel, "build_statistical_baseline")
    assert hasattr(semantic_funnel, "execute_alignment_flow")
