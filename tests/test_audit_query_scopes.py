"""
=============================================================================
Argus Medical Audit - ClickHouse Queryable Scope & Scenario Test Suite
=============================================================================
测试基于真实加载的 ClickHouse 医保审计数据边界，验证各个业务审计场景的可查询范围与判定逻辑：
1. 性别限制冲突（男性使用妇科药品/诊疗项目/避孕节育耗材）
2. 负数结算与退费冲正核查
3. 大额单笔自费与离群值探查
4. 2024 核心就诊结算批次分布与费用守恒校验
5. 规则零发现基线合规判定（同日同人同院重复结算规则）
6. 定点医药机构资质与等级分布
7. 全国医保行政区划四级层级穿透
8. 临床药品目录与剂型生产厂家核查
9. 安全防护门禁（只读安全与 DDL 拦截校验）
=============================================================================
"""

import os
import sys
import pytest
from dotenv import load_dotenv

# 确保加载项目根目录与环境变量
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.core.bootstrap import register_services
register_services()

from app.infra.db_conn import get_clickhouse_client
from app.skills.security import SQLGuardian
from app.core.context.gates import QualityGate


@pytest.fixture(scope="module")
def ck_client():
    """获取 ClickHouse 只读全局客户端"""
    return get_clickhouse_client()


class TestAuditQueryScopes:
    """医保审计可查范围与规则自动化测试套件"""

    def test_gender_conflict_male_gynecological_drugs(self, ck_client):
        """
        场景 1: 性别限制冲突核查 (GENDER_CONFLICT)
        范围: fqz_fymx_test 表，男性患者 (gend='1') 开具妇科/生殖类专属药品
        """
        sql = """
            SELECT 
                replace(hilist_name, '\t', '') AS drug_name,
                count(*) AS record_count,
                count(DISTINCT psn_no) AS patient_count,
                round(sum(det_item_fee_sumamt), 2) AS total_amount
            FROM fqz_fymx_test
            WHERE replace(gend, '\t', '') = '1'
              AND (
                  replace(hilist_name, '\t', '') LIKE '%妇%'
                  OR replace(hilist_name, '\t', '') LIKE '%阴道%'
                  OR replace(hilist_name, '\t', '') LIKE '%宫%'
                  OR replace(hilist_name, '\t', '') LIKE '%雌二醇%'
                  OR replace(hilist_name, '\t', '') LIKE '%孕酮%'
                  OR replace(hilist_name, '\t', '') LIKE '%益母草%'
              )
            GROUP BY drug_name
            ORDER BY record_count DESC
        """
        results = ck_client.query(sql)
        assert len(results) > 0, "应检测到男性开具妇科专属药品的违规明细"

        # 检查重点违规药品益母草颗粒、地屈孕酮片
        drug_names = [r["drug_name"] for r in results]
        assert any("益母草颗粒" in d for d in drug_names), "违规列表中应包含益母草颗粒"
        assert any("地屈孕酮片" in d for d in drug_names), "违规列表中应包含地屈孕酮片"

        total_violations = sum(r["record_count"] for r in results)
        total_amount = sum(r["total_amount"] for r in results)
        assert total_violations >= 4000, f"男性妇科用药记录数应 >= 4000 (实际: {total_violations})"
        assert total_amount >= 200000.0, f"违规金额总额应 >= 20万元 (实际: {total_amount})"

    def test_male_contraceptive_device_fraud(self, ck_client):
        """
        场景 2: 严重性别逻辑冲突 - 男性开具女性专用节育系统耗材
        范围: fqz_fymx_test 中男性 (gend='1') 结算左炔诺孕酮宫内节育系统
        """
        sql = """
            SELECT 
                psn_no,
                replace(hilist_name, '\t', '') AS item_name,
                count(*) AS item_cnt,
                round(sum(det_item_fee_sumamt), 2) AS item_fee
            FROM fqz_fymx_test
            WHERE replace(gend, '\t', '') = '1'
              AND replace(hilist_name, '\t', '') LIKE '%左炔诺孕酮宫内节育系统%'
            GROUP BY psn_no, item_name
        """
        results = ck_client.query(sql)
        assert len(results) > 0, "应核查出男性开具宫内节育系统的异常案例"
        total_fee = sum(r["item_fee"] for r in results)
        assert total_fee == 5880.0, f"男性宫内节育系统费用应为 5880.0 (实际: {total_fee})"

    def test_refund_negative_fee_detection(self, ck_client):
        """
        场景 3: 负数冲正与退费记录核查
        范围: fqz_fymx_test 中费用金额小于 0 的项目明细
        """
        sql = """
            SELECT 
                count(*) AS refund_count,
                round(sum(det_item_fee_sumamt), 2) AS refund_sum,
                min(det_item_fee_sumamt) AS min_amt
            FROM fqz_fymx_test
            WHERE det_item_fee_sumamt < 0
        """
        results = ck_client.query(sql)
        assert len(results) == 1
        row = results[0]
        assert row["refund_count"] > 0, "费用明细中应存在退费冲正记录"
        assert row["refund_sum"] < 0, "退费总额应为负值"
        assert row["min_amt"] == -29.7, f"最大单笔冲正金额应为 -29.7 (实际: {row['min_amt']})"

    def test_high_value_single_fee_outliers(self, ck_client):
        """
        场景 4: 单笔大额费用离群值核查
        范围: fqz_fymx_test 中单笔项目金额 >= 1000.0 元的记录
        """
        sql = """
            SELECT 
                count(*) AS outlier_count,
                max(det_item_fee_sumamt) AS max_fee
            FROM fqz_fymx_test
            WHERE det_item_fee_sumamt >= 1000.0
        """
        results = ck_client.query(sql)
        row = results[0]
        assert row["outlier_count"] > 0, "应检测到超过 1000 元的单笔大额费用"
        assert row["max_fee"] == 1560.0, f"单笔最高费用应为 1560.0 (实际: {row['max_fee']})"

    def test_core_settlement_batches_2024(self, ck_client):
        """
        场景 5: 核心就诊表 2024 年度结算批次分布与费用守恒
        范围: fqz_gz_jzsj_all_ql 表 2,500 条就诊记录的日期与金额验证
        """
        sql = """
            SELECT 
                toDate(setl_time) AS setl_day,
                count(*) AS row_cnt,
                round(sum(medfee_sumamt), 2) AS medfee_sum,
                round(sum(fund_pay_sumamt), 2) AS fund_sum
            FROM fqz_gz_jzsj_all_ql
            GROUP BY setl_day
            ORDER BY setl_day
        """
        results = ck_client.query(sql)
        # 应包含 3 个结算波峰批次 (2024-03-06, 2024-04-11, 2024-04-15)
        assert len(results) == 3, f"结算数据应分布在 3 个批次日期中 (实际: {len(results)})"

        total_rows = sum(r["row_cnt"] for r in results)
        total_medfee = sum(r["medfee_sum"] for r in results)
        assert total_rows == 2500, f"总记录数应严格等于 2500 (实际: {total_rows})"
        assert abs(total_medfee - 348640.30) < 0.01, f"总医疗费用应精确等于 348640.30 (实际: {total_medfee})"

    def test_zero_findings_rule_repeat_billing(self, ck_client):
        """
        场景 6: 零发现基线核查 (ZERO-FINDINGS AUDIT BASELINE)
        规则: REPEAT_BILLING_DETECTOR (同日同人同院多次结算)
        要求: 针对当前数据样本返回 0 条异常，触发零发现安全留痕机制
        """
        sql = """
            SELECT 
                psn_no,
                toDate(setl_time) AS setl_date,
                fixmedins_name,
                count(DISTINCT setl_id) AS setl_count
            FROM fqz_gz_jzsj_all_ql
            WHERE toYear(toDateTime(setl_time)) = 2024
            GROUP BY psn_no, setl_date, fixmedins_name
            HAVING setl_count > 1
        """
        results = ck_client.query(sql)
        assert len(results) == 0, "当前就诊批次中应不存在同日同院重复结算，属于合规零发现"

    def test_hospital_directory_coverage(self, ck_client):
        """
        场景 7: 定点医药机构库范围核查
        范围: fqz_all_yy_yd 表 587 家定点机构与等级分布
        """
        sql = """
            SELECT 
                medins_type,
                count(*) AS total_hosp,
                countIf(medinslv = '2') AS tier2_cnt
            FROM fqz_all_yy_yd
            GROUP BY medins_type
        """
        results = ck_client.query(sql)
        assert len(results) > 0
        total_count = sum(r["total_hosp"] for r in results)
        assert total_count == 587, f"医药机构库总数应为 587 (实际: {total_count})"

    def test_administrative_division_hierarchy(self, ck_client):
        """
        场景 8: 医保行政区划四级穿透核查
        范围: fqz_admdvs 表 4,294 条区划字典
        """
        sql = """
            SELECT 
                admdvs_lv,
                count(*) AS lv_count
            FROM fqz_admdvs
            GROUP BY admdvs_lv
            ORDER BY toInt32OrZero(admdvs_lv)
        """
        results = ck_client.query(sql)
        levels = {r["admdvs_lv"]: r["lv_count"] for r in results}
        assert "0" in levels, "应包含国家级医保区划 (level 0)"
        assert "1" in levels, "应包含省级医保区划 (level 1)"
        assert "2" in levels, "应包含市级医保区划 (level 2)"
        assert "3" in levels, "应包含区县级医保区划 (level 3)"
        total_admdvs = sum(levels.values())
        assert total_admdvs == 4294, f"行政区划总数应为 4294 (实际: {total_admdvs})"

    def test_drug_catalog_specifications(self, ck_client):
        """
        场景 9: 临床药品目录抗生素与厂家核查
        范围: fqz_drug_mcs_info_list 表 47 种目录药品
        """
        sql = """
            SELECT 
                count(*) AS drug_total,
                count(DISTINCT drugstdcode) AS generic_types,
                countIf(drugstdcode LIKE '%头孢%' OR drugstdcode LIKE '%哌拉西林%') AS anti_cnt
            FROM fqz_drug_mcs_info_list
        """
        results = ck_client.query(sql)
        row = results[0]
        assert row["drug_total"] == 47, f"目录药品总数应为 47 (实际: {row['drug_total']})"
        assert row["anti_cnt"] == 29, f"头孢与哌拉西林抗生素品种数应为 29 (实际: {row['anti_cnt']})"

    def test_quality_gate_security_interception(self):
        """
        场景 10: SQL 审计门禁与破坏性 DDL 拦截校验
        验证系统级防护保证：只读查询放行，危险改动拦截
        """
        # 1. 安全合规的审计查询应顺利通过校验并返回清洗后的 SQL
        safe_sql = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test GROUP BY psn_no LIMIT 100"
        sanitized = SQLGuardian.validate_sql(safe_sql)
        assert isinstance(sanitized, str) and "fqz_fymx_test" in sanitized, f"合规只读审计 SQL 应该通过: {sanitized}"

        # 2. 危险的 DROP / TRUNCATE / ALTER 破坏性语句必须被 100% 物理拦截
        dangerous_sql = "DROP TABLE fqz_gz_jzsj_all_ql"
        with pytest.raises(Exception):
            SQLGuardian.validate_sql(dangerous_sql)

        # 3. QualityGate 风险评估与人工审批拦截
        risk = QualityGate.evaluate_risk({"sql_query": dangerous_sql})
        assert risk >= 0.9, f"破坏性 DROP 语句风险应 >= 0.9 (实际: {risk})"
        assert QualityGate.should_trigger_human_approval({"sql_query": dangerous_sql}) is True
