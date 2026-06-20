"""
Unit tests for app/skills/probe_guard.py.
"""
import pytest
from app.skills.probe_guard import is_probe_query, STRUCTURAL_WHITELIST, AGGREGATE_WHITELIST


# -- QA-CUST-26 batch-billing detection SQL patterns --
FYMX_BATCH_SQL = """SELECT toDate(toDateTime(substring(trim(setl_time),1,19))) AS setl_date,
       trim(fixmedins_name) AS inst, trim(hilist_name) AS item,
       count(DISTINCT trim(psn_no)) AS patient_count,
       dateDiff('second', min(toDateTime(substring(trim(setl_time),1,19))),
                         max(toDateTime(substring(trim(setl_time),1,19)))) AS span_sec
FROM default.fqz_fymx_test
WHERE trim(fixmedins_name) LIKE '%卫生%'
GROUP BY setl_date, inst, item
HAVING patient_count >= 5 AND span_sec <= 300
ORDER BY patient_count DESC LIMIT 50"""


class TestMetadataProbes:
    def test_show_tables(self):
        assert is_probe_query("SHOW TABLES") is True

    def test_describe(self):
        assert is_probe_query("DESCRIBE fqz_gz_jzsj_all_ql") is True

    def test_explain(self):
        assert is_probe_query("EXPLAIN SELECT 1") is True

    def test_desc_short(self):
        assert is_probe_query("DESC my_table") is True


class TestCountProbes:
    def test_select_count_star(self):
        assert is_probe_query("SELECT COUNT(*) FROM fqz_gz_jzsj_all_ql") is True

    def test_count_with_paren_space(self):
        assert is_probe_query("SELECT COUNT (*) FROM table") is True

    def test_min_setl_time(self):
        assert is_probe_query("SELECT MIN(SETL_TIME) FROM table") is True

    def test_count_not_probe_with_join(self):
        assert is_probe_query("SELECT COUNT(*) FROM a JOIN b ON a.id = b.id") is False


class TestDistinctDictionaryProbes:
    def test_distinct_med_type(self):
        assert is_probe_query("SELECT DISTINCT MED_TYPE FROM table") is True

    def test_distinct_hilist_name(self):
        assert is_probe_query("SELECT DISTINCT HILIST_NAME FROM table") is True

    def test_distinct_with_join_not_probe(self):
        assert is_probe_query("SELECT DISTINCT a.MED_TYPE FROM a JOIN b ON a.id=b.id") is False


class TestAnalysisWhitelist:
    """[V178.10] Structural constructs (WITH/CTE, CASE WHEN, UNION) always exempt;
    aggregate baselines (quantile/avg without GROUP BY) are probes."""

    def test_quantile_with_groupby_exempt(self):
        """quantile() WITH GROUP BY is whitelisted, not a probe."""
        assert is_probe_query("SELECT dept, quantile(0.95)(medfee) FROM table GROUP BY dept") is False

    def test_quantile_pure_baseline_is_probe(self):
        """[V178.10] Pure quantile() baseline without GROUP BY is a probe."""
        assert is_probe_query("SELECT quantile(0.95)(medfee) FROM table") is True

    def test_stddev_with_groupby_exempt(self):
        """stddevPop() WITH GROUP BY is whitelisted, not a probe."""
        assert is_probe_query("SELECT dept, stddevPop(medfee) FROM table GROUP BY dept") is False

    def test_stddev_pure_baseline_is_probe(self):
        """[V178.10] Pure stddevPop() baseline without GROUP BY is a probe."""
        assert is_probe_query("SELECT stddevPop(medfee) FROM table") is True

    def test_cte_with_exempt(self):
        """[V178.10] CTE (WITH) queries are structural - always exempt."""
        assert is_probe_query("WITH cte AS (SELECT 1) SELECT * FROM cte") is False

    def test_case_when_exempt(self):
        """[V178.10] CASE WHEN is structural - always exempt."""
        assert is_probe_query("SELECT CASE WHEN x THEN 1 ELSE 0 END FROM t") is False

    def test_union_all_exempt(self):
        """[V178.10] UNION ALL is structural - always exempt."""
        assert is_probe_query("SELECT 1 UNION ALL SELECT 2") is False


class TestCust27BaselineProbe:
    """QA-CUST-27: Baseline SQL classification with V178.10 baseline detection."""

    def test_avg_baseline_with_groupby_not_probe(self):
        """Phase 1 baseline with avg() AND GROUP BY must not be a probe."""
        sql = "SELECT avg(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= subtractYears(toDate(now()), 5) GROUP BY setl_id LIMIT 100"
        assert is_probe_query(sql) is False

    def test_sum_aggregation_with_groupby_not_probe(self):
        """SUM() aggregation WITH GROUP BY is legitimate business analysis."""
        sql = "SELECT dept, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' GROUP BY dept"
        assert is_probe_query(sql) is False

    def test_sum_pure_baseline_is_probe(self):
        """[V178.10] Pure SUM() baseline without GROUP BY is a probe."""
        sql = "SELECT sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'"
        assert is_probe_query(sql) is True

    def test_quantile_pure_baseline_is_probe(self):
        """[V178.10] Pure quantile() baseline without GROUP BY is a probe."""
        sql = "SELECT quantile(0.95)(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2021-01-01'"
        assert is_probe_query(sql) is True

    def test_quantile_with_groupby_not_probe(self):
        """quantile() WITH GROUP BY is whitelisted, not a probe."""
        sql = "SELECT dept, quantile(0.95)(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2021-01-01' GROUP BY dept"
        assert is_probe_query(sql) is False

    def test_short_groupby_with_avg_not_probe(self):
        """Short GROUP BY with avg() is whitelisted, not a probe."""
        sql = "SELECT avg(medfee_sumamt) FROM fqz_gz_jzsj_all_ql GROUP BY setl_id"
        assert is_probe_query(sql) is False

    def test_phase2_detail_query_not_probe(self):
        """Phase 2: SELECT ... WHERE medfee_sumamt > threshold ORDER BY ... LIMIT 100 is NOT a probe."""
        sql = "SELECT psn_no, fixmedins_code, medfee_sumamt, setl_id FROM fqz_gz_jzsj_all_ql WHERE setl_time >= subtractYears(today(), 5) AND medfee_sumamt > 213.6 ORDER BY medfee_sumamt DESC LIMIT 100"
        assert is_probe_query(sql) is False

    def test_where_orderby_no_limit_not_probe(self):
        """WHERE + ORDER BY without LIMIT is still a business query, not probe."""
        sql = "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 500 ORDER BY medfee_sumamt DESC"
        assert is_probe_query(sql) is False

    def test_where_only_not_probe(self):
        """WHERE without ORDER BY or LIMIT is still a business query."""
        sql = "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 500"
        assert is_probe_query(sql) is False


class TestRealAuditQueries:
    def test_join_query_not_probe(self):
        sql = "SELECT a.*, b.medfee FROM a JOIN b ON a.id = b.id"
        assert is_probe_query(sql) is False

    def test_group_by_not_probe(self):
        # QA-CUST-27 fix: GROUP BY with no JOIN is now NOT a probe (rule 4 updated)
        assert is_probe_query("SELECT dept, COUNT(*) FROM table GROUP BY dept") is False

    def test_having_not_probe(self):
        # HAVING with COUNT(*) but no JOIN/GROUP BY is caught by rule 2 (count probe)
        assert is_probe_query("SELECT x FROM t HAVING COUNT(*) > 5") is True

    def test_window_not_probe(self):
        assert is_probe_query("SELECT x, ROW_NUMBER() OVER() FROM t") is False

    def test_gender_query_not_probe(self):
        assert is_probe_query("SELECT GEND FROM t") is False


class TestEdgeCases:
    def test_empty_sql_is_probe(self):
        assert is_probe_query("") is True

    def test_none_sql_is_probe(self):
        assert is_probe_query(None) is True

    def test_short_no_join_is_probe(self):
        assert is_probe_query("SELECT * FROM table") is True

    def test_long_query_not_probe(self):
        parts = ["col" + str(i) + " = " + str(i) for i in range(100)]
        long_sql = "SELECT * FROM fqz_gz_jzsj_all_ql WHERE " + " AND ".join(parts)
        assert is_probe_query(long_sql) is False

    def test_simple_limit_probe(self):
        assert is_probe_query("SELECT * FROM table LIMIT 10") is True


class TestCust26BatchBilling:
    """Edge case tests for QA-CUST-26 (batch billing time-series detection)."""

    def test_full_batch_billing_sql_not_probe(self):
        """The canonical QA-CUST-26 SQL (with HAVING) must NOT be classified as probe."""
        assert is_probe_query(FYMX_BATCH_SQL) is False

    def test_batch_billing_with_join_not_probe(self):
        """A JOIN-based variant of the batch billing query must not be a probe."""
        sql = (
            "SELECT A.fixmedins_code, count(DISTINCT A.psn_no) AS cnt "
            "FROM fqz_gz_jzsj_all_ql A "
            "JOIN fqz_fymx_test B ON A.setl_id = B.setl_id "
            "GROUP BY A.fixmedins_code HAVING cnt >= 5"
        )
        assert is_probe_query(sql) is False

    def test_long_groupby_having_not_probe(self):
        """A long (>500 char) GROUP BY + HAVING query without JOIN must not be a probe."""
        padding = " AND " + " AND ".join(f"col{i} IS NOT NULL" for i in range(30))
        sql = (
            "SELECT trim(fixmedins_name) AS inst, count(DISTINCT psn_no) AS cnt "
            "FROM fqz_fymx_test WHERE 1=1" + padding +
            " GROUP BY inst HAVING cnt >= 5"
        )
        assert is_probe_query(sql) is False

    def test_short_groupby_no_having_is_probe(self):
        """QA-CUST-27 fix: Short GROUP BY is now NOT a probe (rule 4 updated)."""
        sql = "SELECT dept, count(*) FROM fqz_fymx_test GROUP BY dept"
        assert is_probe_query(sql) is False

    def test_timestamp_heal_function(self):
        """The _heal_timestamp_tab function correctly wraps bare toDateTime."""
        from app.skills.sql_tools import _heal_timestamp_tab
        raw = "SELECT toDateTime(setl_time) FROM fqz_fymx_test"
        healed = _heal_timestamp_tab(raw)
        assert "substring(trim(setl_time),1,19)" in healed
        assert healed != raw

    def test_timestamp_heal_no_double_wrap(self):
        """Already-wrapped toDateTime must not be double-wrapped."""
        from app.skills.sql_tools import _heal_timestamp_tab
        already_wrapped = (
            "SELECT toDateTime(substring(trim(setl_time),1,19)) FROM fqz_fymx_test"
        )
        healed = _heal_timestamp_tab(already_wrapped)
        assert healed == already_wrapped

    def test_timestamp_heal_table_qualified(self):
        """Table-qualified column names are handled correctly."""
        from app.skills.sql_tools import _heal_timestamp_tab
        raw = "SELECT toDateTime(A.setl_time) FROM fqz_gz_jzsj_all_ql A"
        healed = _heal_timestamp_tab(raw)
        assert "substring(trim(A.setl_time),1,19)" in healed
        assert healed != raw

    def test_timestamp_heal_idempotent(self):
        """Running heal twice produces the same result."""
        from app.skills.sql_tools import _heal_timestamp_tab
        raw = "SELECT toDateTime(setl_time) FROM t"
        once = _heal_timestamp_tab(raw)
        twice = _heal_timestamp_tab(once)
        assert once == twice
