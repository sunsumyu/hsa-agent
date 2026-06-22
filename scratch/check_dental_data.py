# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def run():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    ya = b'\xe7\x89\x99'.decode('utf-8')
    kouqiang = b'\xe5\x8f\xa3\xe8\x85\x94'.decode('utf-8')
    ba = b'\xe6\x8b\xb4'.decode('utf-8')
    
    queries = [
        f"SELECT count() FROM default.fqz_gz_jzsj_all_ql WHERE dise_name LIKE '%{ya}%'",
        f"SELECT count() FROM default.fqz_gz_jzsj_all_ql WHERE dise_name LIKE '%{kouqiang}%'",
        f"SELECT count() FROM default.fqz_gz_jzsj_all_ql WHERE oprn_oprt_name LIKE '%{ya}%'",
        f"SELECT count() FROM default.fqz_gz_jzsj_all_ql WHERE oprn_oprt_name LIKE '%{ba}%'"
    ]
    for q in queries:
        try:
            cnt = client.execute(q)[0][0]
            print(f"Query: {q} -> {cnt} rows")
        except Exception as e:
            print(f"Query failed -> {e}")

if __name__ == "__main__":
    run()
