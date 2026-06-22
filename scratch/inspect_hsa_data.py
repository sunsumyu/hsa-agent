import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    print("=== fqz_hsa.fqz_gz_jzsj_all_ql Sample ===")
    r = client.query("SELECT * FROM fqz_hsa.fqz_gz_jzsj_all_ql LIMIT 10")
    for idx, row in enumerate(r):
        print(f"Row {idx}:")
        for k, v in row.items():
            if v:
                print(f"  {k}: {repr(v)}")
                
    print("\n=== fqz_hsa.fqz_fymx_test Sample ===")
    r = client.query("SELECT * FROM fqz_hsa.fqz_fymx_test LIMIT 10")
    for idx, row in enumerate(r):
        print(f"Row {idx}:")
        for k, v in row.items():
            if v:
                print(f"  {k}: {repr(v)}")

if __name__ == '__main__':
    main()
