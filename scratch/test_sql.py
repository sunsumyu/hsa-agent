import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

def test_agent_sql():
    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=int(os.getenv("CLICKHOUSE_PORT")),
        username=os.getenv("CLICKHOUSE_USER"),
        password=os.getenv("CLICKHOUSE_PASSWORD")
    )
    # Agent 生成的 SQL
    sql = """
    SELECT psn_no, count(*) 
    FROM fqz_gz_jzsj_all_ql 
    WHERE psn_no = '52000001000000003004108338' AND toYear(toDate(start_date)) = 2024
    GROUP BY psn_no
    """
    res = client.query(sql)
    print(f"Result: {res.result_rows}")

if __name__ == "__main__":
    test_agent_sql()
