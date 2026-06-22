import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def decode_items():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    query = """
        SELECT hilist_name, hex(hilist_name), count() 
        FROM default.fqz_fymx_test 
        GROUP BY hilist_name
    """
    try:
        res = client.execute(query)
        print(f"Total distinct items: {len(res)}")
        for idx, row in enumerate(res):
            raw_name, hex_val, count = row
            try:
                decoded = bytes.fromhex(hex_val).decode('utf-8').strip()
            except Exception as e:
                decoded = f"UTF-8 decode failed: {e}"
            print(f"Item {idx+1}: {hex_val}")
            print(f"  -> Decoded: {repr(decoded)} (Count: {count})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    decode_items()
