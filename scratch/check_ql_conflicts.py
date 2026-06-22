import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def check_ql_conflicts():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password='', database='default'
    )
    
    print(">>> Searching for diagnosis-gender conflicts in default.fqz_gz_jzsj_all_ql:")
    
    # 1. Male with female diagnosis
    query1 = """
        SELECT psn_name, gend, dise_name, medfee_sumamt, fixmedins_name 
        FROM default.fqz_gz_jzsj_all_ql 
        WHERE (trim(gend) = '1') AND (
            dise_name LIKE '%妇科%' 
            OR dise_name LIKE '%产科%' 
            OR dise_name LIKE '%妊娠%' 
            OR dise_name LIKE '%分娩%' 
            OR dise_name LIKE '%子宫%' 
            OR dise_name LIKE '%卵巢%' 
            OR dise_name LIKE '%阴道%'
            OR dise_name LIKE '%胎%'
        )
        LIMIT 10
    """
    
    # 2. Female with male diagnosis
    query2 = """
        SELECT psn_name, gend, dise_name, medfee_sumamt, fixmedins_name 
        FROM default.fqz_gz_jzsj_all_ql 
        WHERE (trim(gend) = '2') AND (
            dise_name LIKE '%前列腺%' 
            OR dise_name LIKE '%睾丸%' 
            OR dise_name LIKE '%包皮%'
        )
        LIMIT 10
    """
    
    try:
        res1 = client.execute(query1)
        print(f"Found {len(res1)} male-to-female diagnosis conflict rows.")
        for row in res1:
            print(f"  - {row}")
            
        res2 = client.execute(query2)
        print(f"Found {len(res2)} female-to-male diagnosis conflict rows.")
        for row in res2:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_ql_conflicts()
