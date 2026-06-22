# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def query_conflict():
    client = get_clickhouse_client()
    
    print(">>> Any rows with non-empty nat_hi_druglist_memo:")
    try:
        res = client.query("SELECT med_list_code, reg_name, nat_hi_druglist_memo FROM default.fqz_drug_mcs_info_list WHERE nat_hi_druglist_memo != ''")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Check if there is any overlap/join between fqz_fymx_test and default.fqz_drug_mcs_info_list:")
    try:
        res = client.query("""
            SELECT A.psn_no, A.gend, A.hilist_code, A.hilist_name, C.nat_hi_druglist_memo
            FROM fqz_fymx_test A
            JOIN default.fqz_drug_mcs_info_list C ON A.hilist_code = C.med_list_code
        """)
        print(f"  - Match count: {len(res)}")
        for row in res[:10]:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Check for gender conflict records in fqz_fymx_test:")
    try:
        # Check where A.gend = '1' (male) but hilist_name contains gynecological/obstetric keywords
        res = client.query("""
            SELECT psn_no, gend, hilist_code, hilist_name, det_item_fee_sumamt 
            FROM fqz_fymx_test 
            WHERE gend = '1' AND (
                hilist_name LIKE '%妇%' 
                OR hilist_name LIKE '%产%' 
                OR hilist_name LIKE '%阴%' 
                OR hilist_name LIKE '%孕%' 
                OR hilist_name LIKE '%宫%' 
                OR hilist_name LIKE '%胎%'
            )
        """)
        print(f"  - Male with Gyn/Obs items count: {len(res)}")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    query_conflict()
