import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Databases in ClickHouse:")
    r = client.query("SHOW DATABASES")
    for row in r:
        print(f"  {row.values()}")

if __name__ == '__main__':
    main()
