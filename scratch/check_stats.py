import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

def check_patient_stats():
    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=int(os.getenv("CLICKHOUSE_PORT")),
        username=os.getenv("CLICKHOUSE_USER"),
        password=os.getenv("CLICKHOUSE_PASSWORD")
    )
    sql = """
    SELECT 
        COUNT(*) as cnt, 
        MAX(medfee_sumamt) as max_fee,
        MIN(start_date),
        MAX(start_date)
    FROM fqz_gz_jzsj_all_ql 
    WHERE psn_no = '52000001000000003004108338' AND toYear(start_date) = 2024
    """
    res = client.query(sql)
    print(f"Stats: {res.result_rows}")

if __name__ == "__main__":
    check_patient_stats()
