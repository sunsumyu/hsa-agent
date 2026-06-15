import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    r = client.query("SELECT min(toDate(replace(setl_time, '\\t', ''))) as min_t, max(toDate(replace(setl_time, '\\t', ''))) as max_t FROM default.fqz_fymx_test")
    print(f"default.fqz_fymx_test setl_time range: {r[0]['min_t']} to {r[0]['max_t']}")

if __name__ == '__main__':
    main()
