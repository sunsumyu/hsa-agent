"""
Red unit tests for safe_math_evaluator and expert_knowledge_retriever deep modules.
"""

import pytest
from app.skills.security.safe_math_evaluator import (
    safe_eval_math_expression,
    is_safe_math_expr,
)
from app.skills.federated.expert_knowledge_retriever import (
    search_expert_knowledge_hints,
    resolve_medical_code_mapping,
)


class TestSafeMathEvaluator:
    def test_basic_arithmetic(self):
        assert safe_eval_math_expression("1 + 2 * 3") == 7.0
        assert safe_eval_math_expression("(10 - 2) / 4") == 2.0
        assert safe_eval_math_expression("2 ** 3") == 8.0
        assert safe_eval_math_expression("10 % 3") == 1.0
        assert safe_eval_math_expression("-5 + 3") == -2.0

    def test_is_safe_math_expr(self):
        assert is_safe_math_expr("123 + 456 / 2") is True
        assert is_safe_math_expr("__import__('os').system('dir')") is False
        assert is_safe_math_expr("math.sin(1)") is False
        assert is_safe_math_expr("") is False

    def test_disallow_unsafe_names_and_calls(self):
        with pytest.raises(ValueError):
            safe_eval_math_expression("import os")
        with pytest.raises(ValueError):
            safe_eval_math_expression("__import__('os')")
        with pytest.raises(ValueError):
            safe_eval_math_expression("abs(-5)")

    def test_pow_dos_guard(self):
        # 常规幂运算仍可用
        assert safe_eval_math_expression("2 ** 10") == 1024.0
        # 指数过大的 DoS 表达式必须被快速拒绝，而不是卡死
        with pytest.raises(ValueError):
            safe_eval_math_expression("9 ** 9 ** 9")

    def test_division_by_zero_raises_valueerror(self):
        # 除零应归一为 ValueError，便于上层统一按“计算失败”处理
        with pytest.raises(ValueError):
            safe_eval_math_expression("1 / 0")


class TestExpertKnowledgeRetriever:
    def test_search_empty_query(self):
        res = search_expert_knowledge_hints("")
        assert "⚠️ 查询为空" in res

    def test_search_matched_or_unmatched(self):
        res = search_expert_knowledge_hints("住院")
        # Should either match expert topic or give helpful message
        assert isinstance(res, str)
        assert len(res) > 0

    def test_resolve_medical_code_mapping(self):
        res = resolve_medical_code_mapping("恶性肿瘤")
        assert isinstance(res, str)
        assert len(res) > 0
