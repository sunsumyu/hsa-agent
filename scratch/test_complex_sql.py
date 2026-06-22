import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

def test_complex_agent_sql():
    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=int(os.getenv("CLICKHOUSE_PORT")),
        username=os.getenv("CLICKHOUSE_USER"),
        password=os.getenv("CLICKHOUSE_PASSWORD")
    )
    # 100% 还原日志中的 Agent SQL
    sql = """
    WITH patient_visits AS (
        SELECT
            psn_no,
            toYear(toDate(start_date)) AS year,
            SUM(medfee_sumamt) AS total_medical_fees,
            COUNT(*) AS visit_count,
            AVG(toUInt32OrZero(ipt_days)) AS avg_stay_days,
            SUM(medfee_sumamt - fund_pay_sumamt) AS personal_payment,
            ROUND(SUM(fund_pay_sumamt) / NULLIF(SUM(medfee_sumamt), 0), 4) AS reimbursement_ratio
        FROM fqz_gz_jzsj_all_ql
        WHERE psn_no = '52000001000000003004108338' AND toYear(toDate(start_date)) = 2024
        GROUP BY psn_no, year
    )
    SELECT
        psn_no,
        total_medical_fees,
        visit_count,
        avg_stay_days,
        personal_payment,
        reimbursement_ratio
    FROM patient_visits
    SETTINGS max_execution_time=30, max_memory_usage=2000000000, max_rows_to_read=5000000, readonly=1
    """
    res = client.query(sql)
    print(f"Result Rows: {res.result_rows}")
    print(f"Column Names: {res.column_names}")

if __name__ == "__main__":
    test_complex_agent_sql()
