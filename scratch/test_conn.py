import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

def test_conn():
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            database=os.getenv("CLICKHOUSE_DB", "default")
        )
        res = client.query("SELECT count() FROM fqz_gz_jzsj_all_ql")
        print(f"Connection Success! Row count: {res.result_rows[0][0]}")
    except Exception as e:
        print(f"Connection Failed: {e}")

if __name__ == "__main__":
    test_conn()
