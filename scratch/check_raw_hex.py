import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def check_hex():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    print(">>> Querying default.fqz_fymx_test with hex representation:")
    query = """
        SELECT psn_name, hex(psn_name), gend, hex(gend), hilist_name, hex(hilist_name), det_item_fee_sumamt 
        FROM default.fqz_fymx_test 
        LIMIT 10
    """
    try:
        res = client.execute(query)
        for row in res:
            psn_name_raw, psn_name_hex, gend_raw, gend_hex, hilist_name_raw, hilist_name_hex, fee = row
            
            # Let's decode hex in Python
            try:
                psn_utf8 = bytes.fromhex(psn_name_hex).decode('utf-8')
            except Exception:
                psn_utf8 = "utf-8 fail"
            try:
                psn_gbk = bytes.fromhex(psn_name_hex).decode('gbk')
            except Exception:
                psn_gbk = "gbk fail"
                
            try:
                hilist_utf8 = bytes.fromhex(hilist_name_hex).decode('utf-8')
            except Exception:
                hilist_utf8 = "utf-8 fail"
            try:
                hilist_gbk = bytes.fromhex(hilist_name_hex).decode('gbk')
            except Exception:
                hilist_gbk = "gbk fail"
                
            print(f"Fee: {fee}")
            print(f"  psn_name hex: {psn_name_hex}")
            print(f"    -> UTF-8: {repr(psn_utf8)}")
            print(f"    -> GBK:   {repr(psn_gbk)}")
            print(f"  hilist_name hex: {hilist_name_hex}")
            print(f"    -> UTF-8: {repr(hilist_utf8)}")
            print(f"    -> GBK:   {repr(hilist_gbk)}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_hex()
