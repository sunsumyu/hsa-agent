import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    # Check counts by year in default.fqz_fymx_test
    r = client.query("SELECT toYear(toDate(replace(setl_time, '\\t', ''))) as y, count() as c FROM default.fqz_fymx_test GROUP BY y")
    print("default.fqz_fymx_test counts by year:")
    for row in r:
        print(f"  Year: {row['y']}, Count: {row['c']}")
        
    # Check match with replace(setl_id, '\t', '')
    r = client.query("""
        SELECT count() as c 
        FROM default.fqz_gz_jzsj_all_ql A
        JOIN default.fqz_fymx_test B ON replace(A.setl_id, '\\t', '') = replace(B.setl_id, '\\t', '')
    """)
    print(f"Matched rows with clean setl_id: {r[0]['c']}")

if __name__ == '__main__':
    main()
