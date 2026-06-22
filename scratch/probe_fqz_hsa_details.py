# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
import json
from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    output = []
    
    output.append("=== fqz_hsa.fqz_gz_jzsj_all_ql ===")
    try:
        res = client.query("SELECT * FROM fqz_gz_jzsj_all_ql")
        output.append(f"Total rows: {len(res)}")
        # Serialize datetime nicely
        def serializer(obj):
            import datetime
            if isinstance(obj, datetime.datetime):
                return obj.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(obj, datetime.date):
                return obj.strftime('%Y-%m-%d')
            return str(obj)
            
        output.append(json.dumps(res, default=serializer, ensure_ascii=False, indent=2))
    except Exception as e:
        output.append(f"Failed: {e}")
        
    output.append("\n=== fqz_hsa.fqz_fymx_test ===")
    try:
        res = client.query("SELECT * FROM fqz_fymx_test")
        output.append(f"Total rows: {len(res)}")
        output.append(json.dumps(res, default=serializer, ensure_ascii=False, indent=2))
    except Exception as e:
        output.append(f"Failed: {e}")

    with open("scratch/fqz_hsa_dump.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    probe()
