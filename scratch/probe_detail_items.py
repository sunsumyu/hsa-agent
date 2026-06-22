# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    output = []
    
    output.append("=== Unique items in fqz_fymx_test ===")
    try:
        res = client.query("SELECT hilist_name, COUNT() as c, SUM(det_item_fee_sumamt) as s FROM fqz_fymx_test GROUP BY hilist_name ORDER BY c DESC LIMIT 200")
        output.append(f"Total unique item names: {len(res)}")
        for r in res:
            output.append(f"  - {repr(r['hilist_name'])}: {r['c']} times, sumamt: {r['s']}")
    except Exception as e:
        output.append(f"Failed: {e}")

    with open("scratch/detail_items.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    probe()
