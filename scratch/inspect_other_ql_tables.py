import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    # 1. fqz_gz_jzsj_all_ql_clean
    r = client.query("SELECT med_type, count() as c FROM default.fqz_gz_jzsj_all_ql_clean GROUP BY med_type")
    print("default.fqz_gz_jzsj_all_ql_clean med_type:")
    for row in r:
        print(f"  {repr(row['med_type'])} : {row['c']}")
        
    # 2. fqz_gz_jzsj_all_ql_fixed
    r = client.query("SELECT med_type, count() as c FROM default.fqz_gz_jzsj_all_ql_fixed GROUP BY med_type")
    print("\ndefault.fqz_gz_jzsj_all_ql_fixed med_type:")
    for row in r:
        print(f"  {repr(row['med_type'])} : {row['c']}")

if __name__ == '__main__':
    main()
