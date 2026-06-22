import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.infra.db_conn import get_clickhouse_client

QUERIES = {
    "1. GENDER_CONFLICT (性别与诊疗冲突)": """
        SELECT
            A.psn_no,
            A.fixmedins_name      AS hospital,
            A.gend                AS gender_code,
            A.hilist_name         AS hilist_name,
            C.nat_hi_druglist_memo AS rule_limit,
            A.det_item_fee_sumamt AS amount,
            A.setl_time           AS setl_time
        FROM fqz_fymx_test A
        LEFT JOIN default.fqz_drug_mcs_info_list C ON replace(A.hilist_code, '\\t', '') = replace(C.med_list_code, '\\t', '')
        WHERE A.setl_time >= '2024-01-01' AND A.setl_time <= '2024-12-31'
          AND replace(A.gend, '\\t', '') = '1'
          AND (
              replace(C.nat_hi_druglist_memo, '\\t', '') LIKE '%限女性%'
              OR replace(A.hilist_name, '\\t', '') LIKE '%妇科%'
              OR replace(A.hilist_name, '\\t', '') LIKE '%产科%'
              OR replace(A.hilist_name, '\\t', '') LIKE '%子宫%'
              OR replace(A.hilist_name, '\\t', '') LIKE '%阴道%'
          )
        ORDER BY A.det_item_fee_sumamt DESC
        LIMIT 10
    """,
    "2. HIGH_FREQ_DRUG_PURCHASE (高频购药异常)": """
        SELECT
            psn_no,
            fixmedins_name AS drug_store,
            count() AS purchase_count,
            min(setl_time) AS first_purchase,
            max(setl_time) AS last_purchase,
            sum(medfee_sumamt) AS sum_medfee_sumamt,
            sum(fund_pay_sumamt) AS sum_fund_pay_sumamt
        FROM fqz_gz_jzsj_all_ql
        WHERE med_type = '定点药店购药'
          AND toYear(toDateTime(setl_time)) = 2024
        GROUP BY psn_no, fixmedins_code, fixmedins_name
        HAVING purchase_count >= 10
        ORDER BY purchase_count DESC
        LIMIT 10
    """,
    "3. CROSS_STORE_HIGH_SPEND (跨药店高消费)": """
        SELECT
            psn_no,
            count(DISTINCT fixmedins_code) AS store_count,
            count() AS total_purchases,
            sum(medfee_sumamt) AS sum_medfee_sumamt,
            sum(fund_pay_sumamt) AS sum_fund_pay_sumamt
        FROM fqz_gz_jzsj_all_ql
        WHERE med_type = '定点药店购药'
          AND toYear(toDateTime(setl_time)) = 2024
        GROUP BY psn_no
        HAVING store_count >= 5 AND sum_fund_pay_sumamt > 5000
        ORDER BY sum_fund_pay_sumamt DESC
        LIMIT 10
    """,
    "4. DECOMPOSITION_HOSPITALIZATION (分解住院/短期高频结算)": """
        SELECT psn_no, fixmedins_name, med_type,
               prev_end_date AS last_setl_date,
               start_date AS curr_setl_date,
               dateDiff('day', toDate(prev_end_date), toDate(start_date)) AS interval_days,
               prev_fee AS last_fee, medfee_sumamt AS curr_fee
        FROM (
            SELECT psn_no, fixmedins_name, fixmedins_code, start_date, end_date,
                   medfee_sumamt, med_type,
                   lag(end_date) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) AS prev_end_date,
                   lag(medfee_sumamt) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) AS prev_fee
            FROM fqz_gz_jzsj_all_ql
            WHERE toYear(toDateTime(start_date)) = 2024
        )
        WHERE prev_end_date IS NOT NULL
          AND dateDiff('day', toDate(prev_end_date), toDate(start_date)) BETWEEN 1 AND 15
        ORDER BY interval_days ASC, curr_fee DESC
        LIMIT 10
    """,
    "5. CROSS_HOSPITAL_OVERLAP (跨机构重复住院)": """
        SELECT
            A.psn_no,
            A.fixmedins_name AS hospital_a,
            B.fixmedins_name AS hospital_b,
            A.start_date AS start_a,
            A.end_date AS end_a,
            B.start_date AS start_b,
            B.end_date AS end_b,
            B.medfee_sumamt AS fee_b
        FROM fqz_gz_jzsj_all_ql A
        JOIN fqz_gz_jzsj_all_ql B ON A.psn_no = B.psn_no
        WHERE A.fixmedins_code != B.fixmedins_code
          AND A.med_type LIKE '%住院%' AND B.med_type LIKE '%住院%'
          AND A.start_date >= '2024-01-01' AND B.start_date >= '2024-01-01'
          AND A.start_date <= B.end_date
          AND B.start_date <= A.end_date
          AND A.setl_id < B.setl_id
        ORDER BY fee_b DESC
        LIMIT 10
    """,
    "6. REPEAT_BILLING_DETECTOR (同日同院重复收费)": """
        SELECT 
            psn_no, 
            toDate(substring(toString(setl_time), 1, 10)) AS setl_date, 
            fixmedins_name,
            count(DISTINCT setl_id) AS visit_count,
            sum(det_item_fee_sumamt) AS total_fee,
            groupArray(setl_id) AS setl_ids
        FROM fqz_fymx_test
        WHERE setl_time >= '2024-01-01' AND setl_time <= '2024-12-31'
        GROUP BY psn_no, toDate(substring(toString(setl_time), 1, 10)), fixmedins_name, fixmedins_code
        HAVING count(DISTINCT setl_id) > 1
        ORDER BY visit_count DESC, total_fee DESC
        LIMIT 10
    """,
    "7. SERVICE_WITHOUT_CONSUMABLE (伴生高值耗材缺失)": """
        SELECT 
            A.setl_id, 
            A.psn_no, 
            A.oprn_oprt_name,
            A.dise_name,
            sum(B.det_item_fee_sumamt) AS total_consumable_fee
        FROM fqz_gz_jzsj_all_ql A 
        LEFT JOIN fqz_fymx_test B ON A.setl_id = B.setl_id 
        WHERE A.setl_time >= '2024-01-01' AND A.setl_time <= '2024-12-31'
          AND (
              replace(A.oprn_oprt_name, '\\t', '') LIKE '%透析%' 
              OR replace(A.oprn_oprt_name, '\\t', '') LIKE '%固定%' 
              OR replace(A.dise_name, '\\t', '') LIKE '%肾衰%' 
              OR replace(A.dise_name, '\\t', '') LIKE '%骨折%'
          ) 
        GROUP BY 
            A.setl_id, 
            A.psn_no, 
            A.oprn_oprt_name,
            A.dise_name
        HAVING 
            -- 逻辑分支 1：血液透析场景，但透析耗材（透析器、管路）缺失
            (
                (replace(A.oprn_oprt_name, '\\t', '') LIKE '%透析%' OR replace(A.dise_name, '\\t', '') LIKE '%肾衰%')
                AND countIf(replace(B.hilist_name, '\\t', '') LIKE '%透析器%' OR replace(B.hilist_name, '\\t', '') LIKE '%管路%') = 0
            )
            OR 
            -- 逻辑分支 2：骨科固定场景，但骨科固定耗材（钛钉、钛板）缺失
            (
                (replace(A.oprn_oprt_name, '\\t', '') LIKE '%固定%' OR replace(A.dise_name, '\\t', '') LIKE '%骨折%')
                AND countIf(replace(B.hilist_name, '\\t', '') LIKE '%钛钉%' OR replace(B.hilist_name, '\\t', '') LIKE '%钛板%') = 0
            )
        ORDER BY total_consumable_fee DESC
        LIMIT 10
    """,
    "8. QA-CUST-23 (理疗医师时间重叠)": """
        SELECT 
            A.chfpdr_name, 
            B.fee_ocur_time, 
            count(DISTINCT A.psn_no) AS psn_count,
            groupArray(A.psn_name) AS psn_names
        FROM fqz_gz_jzsj_all_ql A
        JOIN fqz_fymx_test B ON A.setl_id = B.setl_id
        WHERE B.fee_ocur_time >= '2024-01-01' AND B.fee_ocur_time <= '2024-12-31'
          AND (B.hilist_name LIKE '%手法%' OR B.hilist_name LIKE '%推拿%' OR B.hilist_name LIKE '%按摩%' OR B.hilist_name LIKE '%理疗%')
          AND A.chfpdr_name != ''
        GROUP BY A.chfpdr_name, B.fee_ocur_time
        HAVING psn_count >= 5
        ORDER BY psn_count DESC
        LIMIT 10
    """
}

def run_all_queries():
    print(">>> Connecting to ClickHouse for Direct Year 2024 Tests...")
    try:
        client = get_clickhouse_client()
        print("✅ ClickHouse Connected!")
        
        for name, sql in QUERIES.items():
            print("\n" + "=" * 80)
            print(f"RUNNING: {name}")
            print(f"SQL:\n{sql.strip()}")
            print("-" * 80)
            
            try:
                results = client.query(sql)
                print(f"✅ Executed successfully. Found {len(results)} rows.")
                for idx, row in enumerate(results[:5]):
                    print(f"  Row {idx + 1}: {row}")
            except Exception as e:
                print(f"❌ Execution failed: {e}")
                
    except Exception as e:
        print(f"❌ Direct CK Test failed to connect: {e}")

if __name__ == "__main__":
    run_all_queries()
