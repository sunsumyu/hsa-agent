# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    output = []
    
    output.append("1. Checking non-empty chfpdr_name in fqz_gz_jzsj_all_ql:")
    try:
        res = client.query("SELECT chfpdr_name, COUNT() as c FROM fqz_gz_jzsj_all_ql WHERE chfpdr_name != '' GROUP BY chfpdr_name ORDER BY c DESC LIMIT 100")
        output.append(f"Found {len(res)} unique non-empty doctor names:")
        for r in res:
            output.append(f"  - {repr(r['chfpdr_name'])}: {r['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n2. Checking non-empty adm_dept_name in fqz_gz_jzsj_all_ql:")
    try:
        res = client.query("SELECT adm_dept_name, COUNT() as c FROM fqz_gz_jzsj_all_ql WHERE adm_dept_name != '' GROUP BY adm_dept_name ORDER BY c DESC LIMIT 100")
        output.append(f"Found {len(res)} unique non-empty department names:")
        for r in res:
            output.append(f"  - {repr(r['adm_dept_name'])}: {r['c']}")
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n3. Sample rows where chfpdr_name != '' in fqz_gz_jzsj_all_ql:")
    try:
        res = client.query("SELECT psn_name, gend, adm_dept_name, chfpdr_name, chfpdr_code, dise_name, setl_time FROM fqz_gz_jzsj_all_ql WHERE chfpdr_name != '' LIMIT 20")
        for r in res:
            output.append(f"  - {r}")
    except Exception as e:
        output.append(f"Failed: {e}")

    with open("scratch/probe_res.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    probe()
