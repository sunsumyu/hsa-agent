import os
import clickhouse_connect
from dotenv import load_dotenv

def main():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    print("=== CLICKHOUSE AUDIT DATA PROBE ===")
    
    # 1. QA-NEW-01: 分解住院 (Interval 1-15 days in same hospital)
    sql_decomp = """
    SELECT count() FROM (
        SELECT psn_no, fixmedins_name,
               prev_end_date, start_date,
               dateDiff('day', toDate(prev_end_date), toDate(start_date)) AS interval_days
        FROM (
            SELECT psn_no, fixmedins_name, fixmedins_code, start_date, end_date,
                   medfee_sumamt, med_type,
                   lag(end_date) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) AS prev_end_date
            FROM default.fqz_gz_jzsj_all_ql
            WHERE toYear(toDateTime(start_date)) = 2024
        )
        WHERE prev_end_date IS NOT NULL
          AND med_type NOT LIKE '%药%'
          AND dateDiff('day', toDate(prev_end_date), toDate(start_date)) BETWEEN 1 AND 15
    )
    """
    try:
        res = client.query(sql_decomp)
        print(f"QA-NEW-01 (分解住院) 真实异常条数: {res.first_row[0]}")
    except Exception as e:
        print(f"QA-NEW-01 Error: {e}")

    # 2. QA-NEW-02: 跨定点药店高消费 (Store count >= 5, fund pay > 5000)
    sql_cross_store = """
    SELECT count() FROM (
        SELECT psn_no, count(DISTINCT fixmedins_code) AS store_count,
               sum(fund_pay_sumamt) AS sum_fund_pay
        FROM default.fqz_gz_jzsj_all_ql
        WHERE med_type = '定点药店购药'
          AND toYear(toDateTime(setl_time)) = 2024
        GROUP BY psn_no
        HAVING store_count >= 5 AND sum_fund_pay > 5000
    )
    """
    try:
        res = client.query(sql_cross_store)
        print(f"QA-NEW-02 (跨定点药店高消费) 真实异常条数: {res.first_row[0]}")
    except Exception as e:
        print(f"QA-NEW-02 Error: {e}")

    # 3. QA-NEW-03: 高频购药 (Purchase count >= 10 in same pharmacy)
    sql_high_freq = """
    SELECT count() FROM (
        SELECT psn_no, fixmedins_code, count() AS purchase_count
        FROM default.fqz_gz_jzsj_all_ql
        WHERE med_type = '定点药店购药'
          AND toYear(toDateTime(setl_time)) = 2024
        GROUP BY psn_no, fixmedins_code
        HAVING purchase_count >= 10
    )
    """
    try:
        res = client.query(sql_high_freq)
        print(f"QA-NEW-03 (高频购药) 真实异常条数: {res.first_row[0]}")
    except Exception as e:
        print(f"QA-NEW-03 Error: {e}")

    # 4. QA-NEW-04: 挂床住院 (Inpatient days > 14, fee very low)
    sql_ghost = """
    SELECT count() FROM default.fqz_gz_jzsj_all_ql
    WHERE med_type LIKE '%住院%' 
      AND dateDiff('day', toDate(start_date), toDate(end_date)) > 14
    """
    try:
        res = client.query(sql_ghost)
        print(f"QA-NEW-04 (长住院天数 > 14天患者总数): {res.first_row[0]}")
    except Exception as e:
        print(f"QA-NEW-04 Error: {e}")

    # 5. QA-NEW-05: 跨定点医疗机构同时挂账住院 (Overlapping inpatient dates)
    sql_overlap = """
    SELECT count() FROM (
        SELECT A.psn_no
        FROM default.fqz_gz_jzsj_all_ql A
        JOIN default.fqz_gz_jzsj_all_ql B ON A.psn_no = B.psn_no
        WHERE A.fixmedins_code != B.fixmedins_code
          AND A.med_type LIKE '%住院%' AND B.med_type LIKE '%住院%'
          AND A.start_date >= '2024-01-01' AND B.start_date >= '2024-01-01'
          AND A.start_date <= B.end_date
          AND B.start_date <= A.end_date
          AND A.setl_id < B.setl_id
    )
    """
    try:
        res = client.query(sql_overlap)
        print(f"QA-NEW-05 (跨机构时间重叠住院) 真实异常条数: {res.first_row[0]}")
    except Exception as e:
        print(f"QA-NEW-05 Error: {e}")

    # 6. QA-03: 性别冲突 (Male patients with female drugs/treatments)
    sql_gender = """
    SELECT count()
    FROM default.fqz_fymx_test A
    LEFT JOIN default.fqz_drug_mcs_info_list C ON A.hilist_code = C.med_list_code
    WHERE A.setl_time >= '2024-01-01' AND A.setl_time <= '2024-12-31'
      AND A.gend = '1'
      AND (
          C.nat_hi_druglist_memo LIKE '%限女性%'
          OR A.hilist_name LIKE '%妇科%'
          OR A.hilist_name LIKE '%产科%'
          OR A.hilist_name LIKE '%子宫%'
          OR A.hilist_name LIKE '%阴道%'
      )
    """
    try:
        res = client.query(sql_gender)
        print(f"QA-03 (性别冲突 - 男性妇产科) 真实异常条数: {res.first_row[0]}")
    except Exception as e:
        print(f"QA-03 Error: {e}")

if __name__ == "__main__":
    main()
