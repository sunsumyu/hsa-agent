import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

def debug_query():
    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=int(os.getenv("CLICKHOUSE_PORT")),
        username=os.getenv("CLICKHOUSE_USER"),
        password=os.getenv("CLICKHOUSE_PASSWORD")
    )
    sql = "SELECT psn_no, start_date, toTypeName(start_date) FROM fqz_gz_jzsj_all_ql WHERE psn_no = '52000001000000003004108338' LIMIT 1"
    res = client.query(sql)
    print(res.result_rows)

if __name__ == "__main__":
    debug_query()
