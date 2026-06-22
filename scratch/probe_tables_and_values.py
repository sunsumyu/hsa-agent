# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    
    print(">>> Distinct values of gend in fqz_fymx_test:")
    try:
        res = client.query("SELECT gend, count() FROM fqz_fymx_test GROUP BY gend")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Distinct values of gend in fqz_gz_jzsj_all_ql:")
    try:
        res = client.query("SELECT gend, count() FROM fqz_gz_jzsj_all_ql GROUP BY gend")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Checking if fqz_drug_mcs_info_list exists:")
    try:
        res = client.query("EXISTS fqz_drug_mcs_info_list")
        print(f"  - EXISTS result: {res}")
        if res and res[0][0] == 1:
            desc = client.query("DESCRIBE TABLE fqz_drug_mcs_info_list")
            for row in desc:
                print(f"    - {row}")
    except Exception as e:
        print(f"Error: {e}")
        
    print("\n>>> Let's list some tables in default:")
    try:
        res = client.query("SHOW TABLES")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe()
