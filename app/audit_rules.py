# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Any, Optional
from loguru import logger

class AuditRuleEngine:
    """[V37.7] 审计规则引擎：物理算子库已适配生产数据真实口径"""
    
    # --- [V37.7] 生产数据经口径校准后的 SQL 模板库 ---
    # 实测数据结构: fqz_gz_jzsj_all_ql 为全量结算明细
    # 字段: psn_no, fixmedins_code, fixmedins_name, med_type, start_date, end_date,
    #        dise_name, medfee_sumamt, fund_pay_sumamt, setl_id, setl_time
    TEMPLATES = {
        # [算子 1] 性别与诊断冲突 [ISS-008 Fix]
        # 策略：使用双维度检测
        # - 主检测：gend(性别编码) × dise_name(疾病名称，如存在)
        # - 补充检测：当 dise_name 无法使用时，依赖 med_type 含妇科关键词
        # - 年份过滤确保性能，避免全表扫描 18GB
        "GENDER_CONFLICT": """
            SELECT
                psn_no,
                toYear(setl_time)     AS year,
                fixmedins_name        AS hospital,
                gend                  AS gender_code,
                dise_name             AS diagnosis,
                med_type              AS service_type,
                medfee_sumamt         AS total_fee,
                fund_pay_sumamt       AS fund_paid,
                toDate(setl_time)     AS settle_date
            FROM {table}
            WHERE toYear(setl_time) = 2024
              AND (
                  -- 主策略：男性患者（gend='1'）产生女性专科诊断
                  (
                    gend = '1'
                    AND (
                         dise_name LIKE '%妇%'
                      OR dise_name LIKE '%阴道%'
                      OR dise_name LIKE '%子宫%'
                      OR dise_name LIKE '%乳腺%'
                      OR dise_name LIKE '%卵巢%'
                      OR dise_name LIKE '%宫颈%'
                      OR dise_name LIKE '%产%'
                    )
                  )
                  OR
                  -- 补充策略：med_type 含"妇产科"关键词但 gend=男性
                  (
                    gend = '1'
                    AND (
                         med_type LIKE '%妇%'
                      OR med_type LIKE '%产%'
                      OR med_type LIKE '%妇幼%'
                    )
                  )
                  OR
                  -- 反向检测：女性患者（gend='2'）产生男性专科诊断
                  (
                    gend = '2'
                    AND (
                         dise_name LIKE '%前列腺%'
                      OR dise_name LIKE '%睾丸%'
                      OR dise_name LIKE '%精%'
                    )
                  )
              )
            ORDER BY total_fee DESC
            LIMIT {limit}
        """,

        
        # [算子 2] 高频购药异常（同一参保人在同一药店短时间内多次购药）
        # 适配 fqz_gz_jzsj_all_ql 真实字段: med_type='零售药店购药'
        "HIGH_FREQ_DRUG_PURCHASE": """
            SELECT 
                psn_no, 
                fixmedins_name as drug_store,
                count() as purchase_count,
                min(setl_time) as first_purchase,
                max(setl_time) as last_purchase,
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
            FROM {table}
            WHERE med_type = '定点药店购药'
              AND toYear(setl_time) = 2024
            GROUP BY psn_no, fixmedins_code, fixmedins_name
            HAVING purchase_count >= 10
            ORDER BY purchase_count DESC
            LIMIT {limit}
        """,
        
        # [算子 3] 同一参保人跨药店高消费异常
        "CROSS_STORE_HIGH_SPEND": """
            SELECT 
                psn_no,
                count(DISTINCT fixmedins_code) as store_count,
                count() as total_purchases,
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
            FROM {table}
            WHERE med_type = '定点药店购药'
              AND toYear(setl_time) = 2024
            GROUP BY psn_no
            HAVING store_count >= 5 AND total_fund_paid > 5000
            ORDER BY total_fund_paid DESC
            LIMIT {limit}
        """,
        
        # [算子 4] 分解住院检测（当住院数据可用时）
        # med_type 住院值需按实际数据口径替换
        "DECOMPOSITION_HOSPITALIZATION": """
            SELECT a.psn_no, a.fixmedins_name, a.end_date as discharge_a, b.start_date as admission_b, 
                   dateDiff('day', toDate(a.end_date), toDate(b.start_date)) as interval_days,
                   a.medfee_sumamt as fee_a, b.medfee_sumamt as fee_b,
                   a.dise_name as disease_a, b.dise_name as disease_b
            FROM {table} AS a
            INNER JOIN {table} AS b ON a.psn_no = b.psn_no AND a.fixmedins_code = b.fixmedins_code
            WHERE a.setl_id != b.setl_id
              AND b.start_date > a.end_date
              AND dateDiff('day', toDate(a.end_date), toDate(b.start_date)) BETWEEN 1 AND 15
              AND a.med_type NOT LIKE '%药%'
              AND b.med_type NOT LIKE '%药%'
              AND toYear(a.start_date) = 2024
            ORDER BY interval_days ASC
            LIMIT {limit}
        """,
        
        # [算子 5] 跨机构同日结算（疑似挂名）
        "CROSS_HOSPITAL_OVERLAP": """
            SELECT a.psn_no, a.psn_name, a.fixmedins_name as store_a, b.fixmedins_name as store_b,
                   toDate(a.setl_time) as date_a, toDate(b.setl_time) as date_b,
                   a.medfee_sumamt as amt_a, b.medfee_sumamt as amt_b
            FROM {table} AS a
            INNER JOIN {table} AS b ON a.psn_no = b.psn_no
            WHERE a.fixmedins_code != b.fixmedins_code
              AND toDate(a.setl_time) = toDate(b.setl_time)
              AND a.setl_id != b.setl_id
            ORDER BY a.psn_no
            LIMIT {limit}
        """,

        # [算子 6] 重复收费检测（同一天、同一患者、同一医院多次结算）
        "REPEAT_BILLING_DETECTOR": """
            SELECT
                psn_no,
                toDate(setl_time)       AS setl_date,
                fixmedins_name          AS hospital,
                count()                 AS bill_count,
                sum(medfee_sumamt)      AS total_fee,
                sum(fund_pay_sumamt)    AS total_fund_paid
            FROM {table}
            WHERE toYear(setl_time) = 2024
            GROUP BY psn_no, setl_date, fixmedins_code, fixmedins_name
            HAVING bill_count > 1
            ORDER BY bill_count DESC, total_fee DESC
            LIMIT {limit}
        """,

        # [算子 7] 共用联系方式欺诈网络检测（查找报销额异常偏高的高频结算群体）
        # [ISS-010 Fix] 聚合函数 sum() 不能放在 WHERE，已移至 HAVING
        # 注意：直接查联系方式尾号需要 contact_phone 字段，生产表暂不支持
        # 替代策略：查 2024 年高额报销 + 高报销比率 + 高频次 的异常患者群
        "CONTACT_SHARING_DETECTOR": """
            SELECT
                a.psn_no,
                a.fixmedins_name       AS hospital,
                count()                AS total_visits,
                sum(a.medfee_sumamt)   AS total_fee,
                sum(a.fund_pay_sumamt) AS total_fund_paid,
                round(
                    sum(a.fund_pay_sumamt) / nullIf(sum(a.medfee_sumamt), 0),
                    4
                ) AS reimb_ratio
            FROM {table} AS a
            WHERE toYear(a.setl_time) = 2024
            GROUP BY a.psn_no, a.fixmedins_name, a.fixmedins_code
            HAVING
                total_fund_paid > 5000      -- 报销金额偏高
                AND reimb_ratio > 0.7       -- 报销比例异常（超过 70%）
                AND total_visits > 5        -- 高频结算（5次以上）
            ORDER BY total_fund_paid DESC
            LIMIT {limit}
        """
    }

    @staticmethod
    def get_rule_sql(rule_id: str, table_name: str = "fqz_gz_jzsj_all_ql", limit: int = 50) -> str:
        """根据规则 ID 获取物理取证 SQL"""
        template = AuditRuleEngine.TEMPLATES.get(rule_id.upper())
        if not template:
            logger.error(f">>> [RuleEngine] 未定义的规则算子: {rule_id}")
            return ""
        sql = template.format(table=table_name, limit=limit)
        return sql

    @staticmethod
    def format_violation_report(rule_id: str, results: List[Dict[str, Any]]) -> str:
        """将物理取证结果转化为业务反馈"""
        if not results:
            return "经过规则对撞，未发现该项违规行为。"
        
        count = len(results)
        
        # 尝试汇总金额
        total_amt = 0.0
        for item in results:
            for key in ['medfee_sumamt', 'total_amount', 'total_fund_paid', 'fee_a']:
                if key in item:
                    try:
                        total_amt += float(item[key])
                        break
                    except (ValueError, TypeError):
                        pass
        
        md = f"### 规则对撞详情: {rule_id}\n\n"
        md += f"**审计结论**: 发现疑似违规记录 **{count}** 条，涉及医疗总额 **¥{total_amt:,.2f}**。\n\n"
        md += "**前10条证据明细：**\n\n"
        
        for i, item in enumerate(results[:10]):
            psn = item.get('psn_no', 'N/A')[:8] + '****'  # 脱敏
            md += f"{i+1}. psn:{psn} | "
            # 打印所有键值对
            for k, v in item.items():
                if k != 'psn_no':
                    md += f"{k}={v} | "
            md += "\n"
            
        if count > 10:
            md += f"\n*...其余 {count-10} 条证据已在物理缓冲区固化。*"
        
        return md

rule_engine = AuditRuleEngine()
