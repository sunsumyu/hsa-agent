import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def run():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    for t in ('fqz_gz_jzsj_all_ql', 'fqz_fymx_test'):
        try:
            res = client.execute(f"DESCRIBE TABLE default.{t}")
            print(f"\nColumns for default.{t}:")
            for row in res:
                print(f"  - {row[0]}: {row[1]}")
        except Exception as e:
            print(f"Failed for {t}: {e}")

if __name__ == "__main__":
    run()
