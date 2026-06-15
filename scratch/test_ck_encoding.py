import clickhouse_driver
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

def test_encoding(encoding_name):
    print(f"\n--- Testing with encoding={encoding_name} ---")
    try:
        client = clickhouse_driver.Client(
            host='localhost', port=9000, user='default', password='', database='default',
            encoding=encoding_name
        )
        r = client.execute("SELECT fixmedins_name, count() FROM fqz_gz_jzsj_all_ql GROUP BY fixmedins_name LIMIT 10")
        for row in r:
            val = row[0]
            # Print raw representation
            print(f"  Raw string: {repr(val)}")
            
            # If we used latin1, we can try to decode as gbk or utf-8
            if encoding_name == 'latin1':
                try:
                    dec_gbk = val.encode('latin1').decode('gbk')
                    print(f"    Decoded GBK: {repr(dec_gbk)}")
                except Exception as e:
                    print(f"    Decoded GBK Error: {e}")
                try:
                    dec_utf8 = val.encode('latin1').decode('utf-8')
                    print(f"    Decoded UTF-8: {repr(dec_utf8)}")
                except Exception as e:
                    print(f"    Decoded UTF-8 Error: {e}")
    except Exception as e:
        print(f"Error with {encoding_name}: {e}")

if __name__ == '__main__':
    test_encoding('utf-8')
    test_encoding('latin1')
    test_encoding('gbk')
    test_encoding('gb18030')
