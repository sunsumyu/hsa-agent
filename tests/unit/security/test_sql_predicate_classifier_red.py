"""
Red test for app/core/guardrails/sql_predicate_classifier.py
Testing deep module extraction of SQL AST predicate classification, normalization, and comparable parsing.
"""
import pytest
import sqlglot
from sqlglot import exp

from app.core.guardrails.sql_predicate_classifier import (
    flatten_and,
    classify_predicate,
    parse_comparable_value,
    extract_col_name,
    extract_literal,
)


class TestSqlPredicateClassifierDeepModule:
    def test_flatten_nested_and(self):
        sql = "a = 1 AND (b = 2 AND c = 3)"
        expr = sqlglot.parse_one(sql)
        conjuncts = flatten_and(expr)
        assert len(conjuncts) == 3

    def test_classify_equality_and_inequality(self):
        eq_node = sqlglot.parse_one("gend = '1'")
        col, p_type, val, raw = classify_predicate(eq_node)
        assert col == "gend"
        assert p_type == "EQ"
        assert val == "1"

        neq_node = sqlglot.parse_one("gend != '2'")
        col, p_type, val, raw = classify_predicate(neq_node)
        assert col == "gend"
        assert p_type == "NEQ"
        assert val == "2"

    def test_classify_comparisons(self):
        gt_node = sqlglot.parse_one("fee > 100")
        col, p_type, val, raw = classify_predicate(gt_node)
        assert col == "fee"
        assert p_type == "GT"
        assert val == "100"

        lte_node = sqlglot.parse_one("fee <= 500")
        col, p_type, val, raw = classify_predicate(lte_node)
        assert col == "fee"
        assert p_type == "LTE"
        assert val == "500"

    def test_classify_in_and_is_null(self):
        in_node = sqlglot.parse_one("status IN ('A', 'B')")
        col, p_type, val, raw = classify_predicate(in_node)
        assert col == "status"
        assert p_type == "IN"
        assert val == {"A", "B"}

        null_node = sqlglot.parse_one("psn_no IS NULL")
        col, p_type, val, raw = classify_predicate(null_node)
        assert col == "psn_no"
        assert p_type == "IS_NULL"

    def test_classify_like_and_not_like(self):
        like_node = sqlglot.parse_one("name LIKE '%张%'")
        col, p_type, val, raw = classify_predicate(like_node)
        assert col == "name"
        assert p_type == "LIKE"
        assert val == "%张%"

        not_like_node = sqlglot.parse_one("name NOT LIKE '1%'")
        col, p_type, val, raw = classify_predicate(not_like_node)
        assert col == "name"
        assert p_type == "NOT_LIKE"
        assert val == "1%"

    def test_parse_comparable_value(self):
        assert parse_comparable_value(123.45) == 123.45
        assert parse_comparable_value("678.9") == 678.9
        # Date string to timestamp
        ts = parse_comparable_value("2024-05-01 12:00:00")
        assert ts is not None
        assert ts > 0
        assert parse_comparable_value("invalid_val") is None
