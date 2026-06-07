import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def check_encoding():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password='', database='fqz_hsa'
    )
    print(">>> Raw results from clickhouse_driver:")
    res = client.execute("SELECT hilist_name, gend FROM fqz_fymx_test LIMIT 5")
    for row in res:
        name = row[0]
        gend = row[1]
        print("Raw name:", repr(name), "Type:", type(name), "Gender:", repr(gend))
        if isinstance(name, str):
            try:
                latin1_bytes = name.encode('latin1')
                print("  - Latin1 bytes hex:", latin1_bytes.hex())
                try:
                    print("  - Decoded as GBK:", latin1_bytes.decode('gbk'))
                except Exception as gbk_err:
                    print("  - GBK decode failed:", str(gbk_err))
                try:
                    print("  - Decoded as UTF-8:", latin1_bytes.decode('utf-8'))
                except Exception as utf8_err:
                    print("  - UTF-8 decode failed:", str(utf8_err))
            except Exception as e:
                print("  - Encoding to latin1 failed:", str(e))

if __name__ == "__main__":
    check_encoding()
