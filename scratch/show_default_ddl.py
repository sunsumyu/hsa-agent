import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def show_ddl():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    for table in ["fqz_gz_jzsj_all_ql", "fqz_fymx_test", "fqz_drug_mcs_info_list"]:
        print("=" * 80)
        print(f"CREATE TABLE default.{table}:")
        print("=" * 80)
        try:
            res = client.execute(f"SHOW CREATE TABLE default.{table}")
            print(res[0][0])
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    show_ddl()
