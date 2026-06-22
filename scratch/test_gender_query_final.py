import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def run_query():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    query = """
        SELECT A.psn_no, A.fixmedins_name AS hospital, A.gend, A.hilist_name, A.det_item_fee_sumamt 
        FROM default.fqz_fymx_test A 
        LEFT JOIN default.fqz_drug_mcs_info_list C ON replace(A.hilist_code, '\t', '') = replace(C.med_list_code, '\t', '') 
        WHERE A.setl_time >= '2024-01-01' AND A.setl_time <= '2024-12-31'
          AND replace(A.gend, '\t', '') = '1' 
          AND (
              replace(C.nat_hi_druglist_memo, '\t', '') LIKE '%限女性%' 
              OR replace(A.hilist_name, '\t', '') LIKE '%妇科%' 
              OR replace(A.hilist_name, '\t', '') LIKE '%产科%' 
              OR replace(A.hilist_name, '\t', '') LIKE '%子宫%' 
              OR replace(A.hilist_name, '\t', '') LIKE '%阴道%'
          )
        LIMIT 10
    """
    try:
        res = client.execute(query)
        print(f"Final query returned {len(res)} rows:")
        for row in res:
            cleaned_row = []
            for item in row:
                if isinstance(item, str):
                    cleaned_row.append(item.replace('\t', '\\t'))
                else:
                    cleaned_row.append(item)
            print(f"  - {cleaned_row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_query()
