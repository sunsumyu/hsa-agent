import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Checking fqz_fymx_test...")
    
    # 1. Total rows
    r = client.query("SELECT count() as c FROM default.fqz_fymx_test")
    print(f"Total rows in default.fqz_fymx_test: {r[0]['c']}")
    
    # 2. Match with fqz_gz_jzsj_all_ql on setl_id
    r = client.query("""
        SELECT count(distinct setl_id) as matched_setl_ids, count() as matched_rows 
        FROM default.fqz_fymx_test 
        WHERE setl_id IN (SELECT setl_id FROM default.fqz_gz_jzsj_all_ql)
    """)
    print(f"Matched setl_ids: {r[0]['matched_setl_ids']}, matched rows: {r[0]['matched_rows']}")
    
    # 3. Distinct setl_id count in fqz_fymx_test
    r = client.query("SELECT count(distinct setl_id) as c FROM default.fqz_fymx_test")
    print(f"Distinct setl_ids in fqz_fymx_test: {r[0]['c']}")
    
    # 4. Distinct hilist_name sample
    r = client.query("SELECT hilist_name, count() as c FROM default.fqz_fymx_test GROUP BY hilist_name LIMIT 10")
    print("\nDistinct hilist_name sample in fqz_fymx_test:")
    for row in r:
        val = row['hilist_name']
        try:
            conv = val.encode('latin1').decode('gbk')
        except Exception as e:
            conv = f"<conversion error: {e}>"
        print(f"  Raw: {repr(val)} | Decoded: {repr(conv)} | Count: {row['c']}")

if __name__ == '__main__':
    main()
