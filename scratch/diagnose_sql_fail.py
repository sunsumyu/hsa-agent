import os
import clickhouse_connect
from dotenv import load_dotenv

def diagnose_sql():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    sql = """
    WITH patient_admissions AS (
    SELECT
    psn_no,
    start_date,
    ipt_days
    FROM
    fqz_gz_jzsj_all_ql
    WHERE
    med_type = '住院'
    )

    SELECT
    pa1.psn_no AS patient_id,
    COUNT(pa2.start_date) AS visit_count,
    SUM(pa2.ipt_days) AS total_hospital_days,
    MIN(pa2.start_date) AS first_admission_date,
    MAX(pa2.start_date) AS last_admission_date
    FROM
    patient_admissions pa1
    JOIN
    patient_admissions pa2
    ON
    pa1.psn_no = pa2.psn_no
    AND pa2.start_date >= pa1.start_date
    AND pa2.start_date < DATE_ADD(pa1.start_date, INTERVAL 30 DAY)
    GROUP BY
    pa1.psn_no
    HAVING
    visit_count > 1
    ORDER BY
    visit_count DESC
    LIMIT 1
    """
    
    print(">>> 正在物理执行 SQL...")
    try:
        client.query(sql)
        print("✅ SQL 执行成功！")
    except Exception as e:
        print("❌ SQL 执行失败！内容如下：")
        print("-" * 50)
        print(str(e))
        print("-" * 50)

if __name__ == "__main__":
    diagnose_sql()
