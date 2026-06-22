# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
import json
from app.infra.db_conn import get_clickhouse_client

def dump():
    client = get_clickhouse_client()
    output = []
    
    # 1. Databases
    output.append("=== Databases ===")
    dbs = client.query("SHOW DATABASES")
    output.append(str(dbs))
    
    # 2. Tables in default & fqz_hsa
    for db in ['default', 'fqz_hsa']:
        output.append(f"\n=== Tables in {db} ===")
        tables = client.query(f"SHOW TABLES FROM {db}")
        output.append(str(tables))
        
        for t in tables:
            t_name = t['name']
            output.append(f"\nSchema of {db}.{t_name}:")
            try:
                schema = client.query(f"DESCRIBE TABLE {db}.{t_name}")
                for col in schema:
                    output.append(f"  - {col['name']}: {col['type']}")
            except Exception as e:
                output.append(f"  Failed: {e}")
                
            # Count
            try:
                cnt = client.query(f"SELECT COUNT() as c FROM {db}.{t_name}")
                output.append(f"  Row count: {cnt[0]['c']}")
            except Exception as e:
                output.append(f"  Count failed: {e}")
                
    # 3. Dump samples from fqz_fymx_test and fqz_gz_jzsj_all_ql
    output.append("\n=== Samples of fqz_fymx_test ===")
    try:
        res = client.query("SELECT * FROM fqz_fymx_test LIMIT 10")
        output.append(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n=== Non-empty columns in fqz_gz_jzsj_all_ql ===")
    try:
        # Since it is a large table, let's look at a few rows where some fields might be filled
        res = client.query("SELECT * FROM fqz_gz_jzsj_all_ql WHERE chfpdr_name != '' OR adm_dept_name != '' LIMIT 10")
        output.append(f"Rows with non-empty doctors/departments: {len(res)}")
        if res:
            output.append(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        output.append(f"Failed: {e}")
        
    # Write to a file
    with open("scratch/db_dump.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print("Done writing to scratch/db_dump.txt")

if __name__ == "__main__":
    dump()
