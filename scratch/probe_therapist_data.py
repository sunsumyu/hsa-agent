# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    print("1. Total count in fqz_fymx_test:")
    try:
        res = client.query("SELECT COUNT() as c FROM fqz_fymx_test")
        print(f"  - {res[0]['c']}")
    except Exception as e:
        print(f"Failed: {e}")

    print("2. Samples of hilist_name in fqz_fymx_test:")
    try:
        res = client.query("SELECT hilist_name, COUNT() as c FROM fqz_fymx_test GROUP BY hilist_name ORDER BY c DESC LIMIT 20")
        for row in res:
            print(f"  - {row['hilist_name']}: {row['c']}")
    except Exception as e:
        print(f"Failed: {e}")

    print("3. Check for '推拿', '手法', '康复', '理疗' in fqz_fymx_test:")
    try:
        res = client.query("SELECT hilist_name, COUNT() as c FROM fqz_fymx_test WHERE hilist_name LIKE '%推拿%' OR hilist_name LIKE '%手法%' OR hilist_name LIKE '%康复%' OR hilist_name LIKE '%理疗%' GROUP BY hilist_name ORDER BY c DESC LIMIT 20")
        for row in res:
            print(f"  - {row['hilist_name']}: {row['c']}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    probe()
