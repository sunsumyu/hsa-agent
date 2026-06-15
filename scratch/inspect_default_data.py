import sys
import os
import io

# Safe stdout/stderr for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Querying database fqz_gz_jzsj_all_ql safely...")
    
    # 1. Total rows
    r = client.query("SELECT count() as c FROM default.fqz_gz_jzsj_all_ql")
    print(f"Total rows in default.fqz_gz_jzsj_all_ql: {r[0]['c']}")
    
    # 2. Distinct med_type
    r = client.query("SELECT med_type, count() as c FROM default.fqz_gz_jzsj_all_ql GROUP BY med_type")
    print("\nDistinct med_type:")
    for row in r:
        val = row['med_type']
        # Try to convert from latin1 to gbk if it looks like it was double-encoded
        try:
            conv = val.encode('latin1').decode('gbk')
        except Exception as e:
            conv = f"<conversion error: {e}>"
        print(f"  Raw: {repr(val)} | Decoded: {repr(conv)} | Count: {row['c']}")
            
    # 3. Distinct fixmedins_name sample
    r = client.query("SELECT fixmedins_name, count() as c FROM default.fqz_gz_jzsj_all_ql GROUP BY fixmedins_name LIMIT 10")
    print("\nSample fixmedins_name:")
    for row in r:
        val = row['fixmedins_name']
        try:
            conv = val.encode('latin1').decode('gbk')
        except Exception as e:
            conv = f"<conversion error: {e}>"
        print(f"  Raw: {repr(val)} | Decoded: {repr(conv)} | Count: {row['c']}")
            
    # 4. Show a sample row
    r = client.query("SELECT * FROM default.fqz_gz_jzsj_all_ql LIMIT 1")
    print("\nSample row:")
    if r:
        for k, v in r[0].items():
            print(f"  {k}: {repr(v)}")

if __name__ == '__main__':
    main()
