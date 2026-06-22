"""
test_v2_validation.py
=====================
验证 Enterprise Architecture V2.0 新增门控模块：
- QueryClassifier (意图分类器)
- IntentValidator (意图-方法论一致性校验)
- SQLSemanticsChecker (SQL 语义检查器)
- HistoryContextFilter (历史便签智能过滤器)
"""

import pytest
import sys
import os

# 确保 Python 能找到项目根目录
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.query_classifier import query_classifier, QueryType
from app.core.intent_validator import intent_validator
from app.core.sql_semantics import sql_semantics_checker
from app.core.history_filter import history_context_filter

class TestQueryClassifier:
    """测试问题类型分类器"""

    def test_classify_ranking(self):
        query = "查最近5年单次结算金额排名最高的异常案件"
        q_type = query_classifier.classify(query)
        assert q_type == QueryType.RANKING

    def test_classify_aggregation(self):
        query = "汇总所有药店的结算总额"
        q_type = query_classifier.classify(query)
        assert q_type == QueryType.AGGREGATION

    def test_classify_threshold(self):
        query = "查异常大额的药店购药结算"
        q_type = query_classifier.classify(query)
        assert q_type == QueryType.THRESHOLD_FILTER


class TestIntentValidator:
    """测试意图-方法论校验器"""

    def test_validate_ranking_with_quantile_methodology(self):
        # 排名类问题如果搞前置分位数计算，应该被拦截
        res = intent_validator.validate_alignment(
            original_query="查最近5年单次结算金额排名最高的异常案件",
            query_type=QueryType.RANKING,
            methodology="先计算全省购药的95%分位数基线，然后把金额大于基线的过滤并汇总...",
            threshold_decision={}
        )
        assert not res["passed"]
        assert "基线" in res["msg"] or "分位数" in res["msg"]

    def test_validate_ranking_with_groupby_methodology(self):
        # 排名类问题如果搞 GROUP BY 分组汇总，应该被拦截
        res = intent_validator.validate_alignment(
            original_query="查单次结算金额排名最高的异常案件",
            query_type=QueryType.RANKING,
            methodology="将结算数据按医院和患者分组进行 group by 汇总...",
            threshold_decision={}
        )
        assert not res["passed"]
        assert "GROUP BY" in res["msg"] or "分组" in res["msg"]

    def test_validate_correct_ranking_methodology(self):
        # 正确的直接排序方法论，应该通过
        res = intent_validator.validate_alignment(
            original_query="查单次结算金额排名最高的异常案件",
            query_type=QueryType.RANKING,
            methodology="直接查询 fqz_gz_jzsj_all_ql 表，按 medfee_sumamt 字段进行降序排序，取前 100 条记录",
            threshold_decision={}
        )
        assert res["passed"]


class TestSQLSemanticsChecker:
    """测试 SQL 语义预检查器"""

    def test_ranking_query_with_groupby_sql(self):
        # 排名类查询不允许有 GROUP BY 聚合 SQL
        sql = "SELECT psn_no, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql GROUP BY psn_no"
        res = sql_semantics_checker.validate(
            sql=sql,
            query_type=QueryType.RANKING,
            methodology="直接排序"
        )
        assert not res["passed"]
        assert "GROUP BY" in res["error"]

    def test_groupby_monetary_field(self):
        # 禁止 GROUP BY 金额字段
        sql = "SELECT count(*) FROM fqz_gz_jzsj_all_ql GROUP BY medfee_sumamt"
        res = sql_semantics_checker.validate(
            sql=sql,
            query_type=QueryType.THRESHOLD_FILTER,
            methodology="按金额分组统计"
        )
        assert not res["passed"]
        assert "medfee_sumamt" in res["error"].lower()

    def test_single_settlement_missing_setl_id(self):
        # 单次结算的聚合问题，GROUP BY 必须包含 setl_id
        sql = "SELECT psn_no, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql GROUP BY psn_no"
        res = sql_semantics_checker.validate(
            sql=sql,
            query_type=QueryType.THRESHOLD_FILTER,
            methodology="核查单次结算中偏高额的数据"
        )
        assert not res["passed"]
        assert "setl_id" in res["error"].lower()


class TestHistoryContextFilter:
    """测试历史上下文过滤器"""

    def test_filter_matching_type_note(self):
        # 当前是 RANKING，过滤掉包含 GROUP BY 的历史便签
        notes = (
            "## 📌 [SQL_EVIDENCE] - 2026-06-20 03:00:00\n"
            "SELECT psn_no, sum(medfee_sumamt) FROM fqz_gz_jzsj_all_ql GROUP BY psn_no ORDER BY sum(medfee_sumamt) DESC"
        )
        filtered = history_context_filter.filter_relevant_notes(
            notes_raw=notes,
            current_query="排名最高",
            query_type=QueryType.RANKING
        )
        assert filtered == ""

    def test_filter_decay_old_notes(self):
        # 超过 30 天的便签降权，超过 90 天的抛弃
        now = datetime_to_str = (
            lambda days: (
                datetime_format := "%Y-%m-%d %H:%M:%S",
                (datetime_now := (datetime_val := __import__("datetime").datetime.now()) - __import__("datetime").timedelta(days=days)).strftime(datetime_format)
            )[1]
        )
        
        # 1. 超过35天，触发30天降权
        notes_35d = f"## 📌 [SQL_EVIDENCE] - {datetime_to_str(35)}\n此条便签用于测试"
        filtered_35d = history_context_filter.filter_relevant_notes(
            notes_raw=notes_35d,
            current_query="大额核查",
            query_type=QueryType.THRESHOLD_FILTER
        )
        assert "已衰减便签" in filtered_35d

        # 2. 超过95天，触发90天丢弃
        notes_95d = f"## 📌 [SQL_EVIDENCE] - {datetime_to_str(95)}\n此条便签用于测试过时抛弃"
        filtered_95d = history_context_filter.filter_relevant_notes(
            notes_raw=notes_95d,
            current_query="大额核查",
            query_type=QueryType.THRESHOLD_FILTER
        )
        assert filtered_95d == ""


class TestReportRendererRestricted:
    """测试报告渲染器在执行受限/逃生舱激活时的去幻觉表现"""

    def test_restricted_report_rendering(self):
        from app.reporting.report_renderer import report_renderer
        rendered = report_renderer.render(
            user_question="查最近5年单次结算金额排名最高的异常个案，看看哪些医院和患者频繁出现大额结算",
            llm_conclusion="由于意图校验逻辑冲突，本次执行受限。",
            raw_data=[],
            sql_query=None,
            sql_history=[],
            table_info="fqz_gz_jzsj_all_ql",
            total_amount=0.0,
            finding_count=0,
            execution_trace=[],
            methodology="排名核查",
            is_restricted=True
        )
        
        # 1. 确保核心 SQL 没有被编造伪造，而是显示受限声明
        assert "[受限核查]" in rendered.markdown
        # 2. 确保没有编造 2,138,354 行扫描数据
        assert "2,138,354" not in rendered.markdown
        assert "物理扫描基数为 0 行" in rendered.markdown
        # 3. 检查数据发现章节是否有受限提示
        assert "由于 SQL 执行受限，本次未检出任何明细数据" in rendered.markdown


# 针对 TestIntentValidator 与 TestSQLSemanticsChecker 的新复合测试用例

def test_validate_ranking_with_groupby_composite():
    res = intent_validator.validate_alignment(
        original_query="查最近5年单次结算金额排名最高的异常个案，看看哪些医院和患者频繁出现大额结算",
        query_type=QueryType.RANKING,
        methodology="使用 GROUP BY 对医院和患者进行分组，计算大额频次并进行降序排列",
        threshold_decision={}
    )
    assert res["passed"]

def test_ranking_query_with_groupby_composite():
    sql = "SELECT psn_no, count(*) FROM fqz_gz_jzsj_all_ql GROUP BY psn_no"
    res = sql_semantics_checker.validate(
        sql=sql,
        query_type=QueryType.RANKING,
        methodology="使用 GROUP BY 统计频繁发生的频次"
    )
    assert res["passed"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
