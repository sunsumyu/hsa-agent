import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.infra.db_conn import get_clickhouse_client

try:
    client = get_clickhouse_client()
    print("SUCCESS: Connected to ClickHouse")
except Exception as e:
    print(f"FAILED: {e}")
