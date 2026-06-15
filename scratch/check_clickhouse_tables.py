import sys
import os
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    res = client.query("SELECT database, name, total_rows FROM system.tables WHERE database IN ('default', 'fqz_hsa')")
    for r in res:
        print(f"DB: {r['database']}, Table: {r['name']}, Rows: {r['total_rows']}")

if __name__ == '__main__':
    main()
