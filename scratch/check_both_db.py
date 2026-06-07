import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def check_both():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    print(">>> Rows in default.fqz_fymx_test:")
    try:
        res = client.execute("SELECT psn_name, gend, hilist_name, det_item_fee_sumamt FROM default.fqz_fymx_test")
        for row in res:
            # Print representation to see exact characters
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n>>> Rows in fqz_hsa.fqz_fymx_test:")
    try:
        res = client.execute("SELECT psn_name, gend, hilist_name, det_item_fee_sumamt FROM fqz_hsa.fqz_fymx_test")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_both()
