import clickhouse_driver
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

def test_table(table_name):
    print(f"\n--- Testing table {table_name} with strings_as_bytes=True ---")
    try:
        client = clickhouse_driver.Client(
            host='localhost', port=9000, user='default', password='', database='default',
            settings={'strings_as_bytes': True}
        )
        r = client.execute(f"SELECT fixmedins_name, count() FROM {table_name} GROUP BY fixmedins_name LIMIT 10")
        for row in r:
            val = row[0]
            print(f"  Raw bytes: {repr(val)}")
            try:
                dec_gbk = val.decode('gbk')
                print(f"    Decoded GBK: {repr(dec_gbk)}")
            except Exception as e:
                print(f"    Decoded GBK Error: {e}")
            try:
                dec_utf8 = val.decode('utf-8')
                print(f"    Decoded UTF-8: {repr(dec_utf8)}")
            except Exception as e:
                print(f"    Decoded UTF-8 Error: {e}")
    except Exception as e:
        print(f"Error with {table_name}: {e}")

if __name__ == '__main__':
    test_table('default.fqz_gz_jzsj_all_ql_clean')
    test_table('default.fqz_gz_jzsj_all_ql_fixed')
