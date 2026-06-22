# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    output = []
    
    # We want to check the "default" database tables
    output.append("=== fqz_gz_jzsj_all_ql in default database ===")
    try:
        res = client.query("SELECT count() as c FROM default.fqz_gz_jzsj_all_ql")
        output.append(f"Total rows in default.fqz_gz_jzsj_all_ql: {res[0]['c']}")
        
        res = client.query("SELECT count() as c FROM default.fqz_gz_jzsj_all_ql WHERE setl_id != ''")
        output.append(f"Rows with non-empty setl_id: {res[0]['c']}")
        
        res = client.query("SELECT count() as c FROM default.fqz_gz_jzsj_all_ql WHERE chfpdr_name != ''")
        output.append(f"Rows with non-empty chfpdr_name: {res[0]['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n=== fqz_fymx_test in default database ===")
    try:
        res = client.query("SELECT count() as c FROM default.fqz_fymx_test")
        output.append(f"Total rows in default.fqz_fymx_test: {res[0]['c']}")
        
        res = client.query("SELECT count() as c FROM default.fqz_fymx_test WHERE setl_id != ''")
        output.append(f"Rows with non-empty setl_id: {res[0]['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n=== Matching setl_id count between default tables ===")
    try:
        res = client.query("SELECT count() as c FROM default.fqz_gz_jzsj_all_ql a INNER JOIN default.fqz_fymx_test b ON a.setl_id = b.setl_id")
        output.append(f"Matching rows count: {res[0]['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n=== Unique items in default.fqz_fymx_test ===")
    try:
        res = client.query("SELECT hilist_name, count() as c FROM default.fqz_fymx_test GROUP BY hilist_name ORDER BY c DESC LIMIT 20")
        for r in res:
            output.append(f"  - {repr(r['hilist_name'])}: {r['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")

    with open("scratch/default_db_probe.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    probe()
