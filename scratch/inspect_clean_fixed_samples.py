import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    print("=== fqz_gz_jzsj_all_ql_clean Sample ===")
    r = client.query("SELECT * FROM default.fqz_gz_jzsj_all_ql_clean LIMIT 1")
    if r:
        for k, v in r[0].items():
            if v:
                print(f"  {k}: {repr(v)}")
                
    print("\n=== fqz_gz_jzsj_all_ql_fixed Sample ===")
    r = client.query("SELECT * FROM default.fqz_gz_jzsj_all_ql_fixed LIMIT 1")
    if r:
        for k, v in r[0].items():
            if v:
                print(f"  {k}: {repr(v)}")

if __name__ == '__main__':
    main()
