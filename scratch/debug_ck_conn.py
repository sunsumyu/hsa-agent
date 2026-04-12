import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
port = int(os.getenv("CLICKHOUSE_PORT", "8123"))

print(f"DEBUG: Attempting clickhouse-connect to {host}:{port}")

try:
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username="",
        password="",
        database="default"
    )
    print("SUCCESS: Connected to ClickHouse!")
    res = client.query("SELECT 1")
    print(f"QUERY SUCCESS: {res.result_rows}")
except Exception as e:
    print(f"FAILURE: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
