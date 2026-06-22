# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    output = []
    
    output.append("=== Doctor Rows ===")
    try:
        # Get all rows with non-empty doctor names
        res = client.query("SELECT psn_no, psn_name, setl_id, fixmedins_name, adm_dept_code, adm_dept_name, chfpdr_code, chfpdr_name, setl_time, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE chfpdr_name != ''")
        output.append(f"Total non-empty doctor rows: {len(res)}")
        for r in res:
            output.append(f"  - {r}")
            # Query fqz_fymx_test for this setl_id
            setl_id = r['setl_id']
            if setl_id:
                details = client.query(f"SELECT * FROM fqz_fymx_test WHERE setl_id = '{setl_id}'")
                output.append(f"    Details count: {len(details)}")
                for d in details:
                    output.append(f"      * {d}")
    except Exception as e:
        output.append(f"Failed: {e}")

    # Also search for '推拿', '手法', '理疗', '康复' in fqz_gz_jzsj_all_ql
    output.append("\n=== Keywords in fqz_gz_jzsj_all_ql ===")
    try:
        res = client.query("SELECT dise_name, count() as c FROM fqz_gz_jzsj_all_ql WHERE dise_name LIKE '%理疗%' OR dise_name LIKE '%康复%' OR dise_name LIKE '%推拿%' OR dise_name LIKE '%手法%' GROUP BY dise_name")
        output.append(f"Found {len(res)} unique matching diagnoses:")
        for r in res:
            output.append(f"  - {r}")
    except Exception as e:
        output.append(f"Failed: {e}")

    # Also check if there are other tables like fqz_gz_jzsj_all_ql_fixed or clean
    for suffix in ['_clean', '_fixed']:
        output.append(f"\n=== Doctor Rows in fqz_gz_jzsj_all_ql{suffix} ===")
        try:
            res = client.query(f"SELECT COUNT() as c FROM fqz_gz_jzsj_all_ql{suffix} WHERE chfpdr_name != ''")
            output.append(f"  - {res[0]['c']} rows")
        except Exception as e:
            output.append(f"  - Failed: {e}")

    with open("scratch/doctor_details.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    probe()
