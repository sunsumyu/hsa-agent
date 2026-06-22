import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    r = client.query("SELECT * FROM default.fqz_fymx_test LIMIT 5")
    for idx, row in enumerate(r):
        print(f"Row {idx}:")
        for k, v in row.items():
            print(f"  {k}: {repr(v)}")

if __name__ == '__main__':
    main()
