# tests/unit/test_quality_gate.py
import pytest
from app.core.context.gates import QualityGate


class TestQualityGateTaskArchetype:
    """TDD 针对 Task Archetype 与 QualityGate SQL 语义不变式守门测试"""

    def test_reconciliation_archetype_rejects_limit_sampling(self):
        """对账任务必须使用聚合，严禁抽样 LIMIT 截断"""
        state = {
            "original_question": "帮我汇总一下2024年医保就诊结算的总体情况，按不同的结算日期统计结算人次、医疗总费用和医保统筹基金支付金额，做个资金对账。"
        }
        # 带有 LIMIT 抽样但无 GROUP BY 聚合的 SQL
        bad_sql = "SELECT setl_id, psn_no, setl_time, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' LIMIT 10"
        res = QualityGate.validate_sql_semantics(state, bad_sql)
        assert res["passed"] is False
        assert "对账" in res["error"] or "聚合" in res["error"]

    def test_reconciliation_archetype_accepts_group_by_aggregation(self):
        """对账任务使用标准 GROUP BY 聚合时放行"""
        state = {
            "original_question": "帮我汇总一下2024年医保就诊结算的总体情况，按不同的结算日期统计结算人次、医疗总费用和医保统筹基金支付金额，做个资金对账。"
        }
        good_sql = "SELECT toDate(setl_time) AS setl_date, count(DISTINCT setl_id) AS cnt, sum(medfee_sumamt) AS total FROM fqz_gz_jzsj_all_ql WHERE toYear(setl_time) = 2024 GROUP BY setl_date ORDER BY setl_date"
        res = QualityGate.validate_sql_semantics(state, good_sql)
        assert res["passed"] is True
        assert res["error"] is None

    def test_inventory_archetype_rejects_limit_sampling(self):
        """层级分布/名录盘点任务，严禁明细抽样 LIMIT 截断"""
        state = {
            "original_question": "我想了解医保行政区划字典的层级划分，系统里国家级、省级、地市级和区县级各有多少个行政区划？"
        }
        bad_sql = "SELECT admdvs, admdvs_name, prnt_admdvs FROM fqz_admdvs WHERE admdvs_lv = '2' LIMIT 30"
        res = QualityGate.validate_sql_semantics(state, bad_sql)
        assert res["passed"] is False
        assert "层级" in res["error"] or "盘点" in res["error"] or "GROUP BY" in res["error"]

    def test_inventory_archetype_accepts_group_by(self):
        """层级分布使用 GROUP BY 全量计数时放行"""
        state = {
            "original_question": "我想了解医保行政区划字典的层级划分，系统里国家级、省级、地市级和区县级各有多少个行政区划？"
        }
        good_sql = "SELECT admdvs_lv, count(*) AS count FROM fqz_admdvs GROUP BY admdvs_lv ORDER BY admdvs_lv"
        res = QualityGate.validate_sql_semantics(state, good_sql)
        assert res["passed"] is True
        assert res["error"] is None

    def test_forensics_archetype_allows_limit(self):
        """单点案件调查取证任务，允许并鼓励安全的 LIMIT 100 采样"""
        state = {
            "original_question": "排查全市男性患者开具妇科专属药品的违规用药情况，列出具体的违规药品明细"
        }
        forensics_sql = "SELECT psn_no, fixmedins_name, hilist_name, det_item_fee_sumamt FROM fqz_fymx_test WHERE gend LIKE '1%' LIMIT 100"
        res = QualityGate.validate_sql_semantics(state, forensics_sql)
        assert res["passed"] is True
        assert res["error"] is None

    def test_ddl_and_injection_high_risk(self):
        """高危 DDL 指令必须被 QualityGate 评估为高风险并触发人工审批拦截"""
        dangerous_sql = "DROP TABLE fqz_gz_jzsj_all_ql"
        risk = QualityGate.evaluate_risk({"sql_query": dangerous_sql})
        assert risk >= 0.9
        assert QualityGate.should_trigger_human_approval({"sql_query": dangerous_sql}) is True
