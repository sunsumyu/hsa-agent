# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def query_records():
    client = get_clickhouse_client()
    
    print(">>> All rows in fqz_hsa.fqz_fymx_test:")
    try:
        res = client.query("SELECT * FROM fqz_fymx_test")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Count of default.fqz_drug_mcs_info_list:")
    try:
        res = client.query("SELECT count(*) FROM default.fqz_drug_mcs_info_list")
        print(f"  - Count: {res}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Sample rows from default.fqz_drug_mcs_info_list:")
    try:
        res = client.query("SELECT * FROM default.fqz_drug_mcs_info_list LIMIT 10")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    query_records()
