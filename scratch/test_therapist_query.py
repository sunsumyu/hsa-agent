# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def test_query():
    client = get_clickhouse_client()
    sql = """
    SELECT A.chfpdr_name, B.fee_ocur_time, COUNT(DISTINCT A.psn_no) AS psn_count
    FROM fqz_gz_jzsj_all_ql A
    INNER JOIN fqz_fymx_test B ON A.setl_id = B.setl_id
    WHERE (B.hilist_name LIKE '%推拿%' OR B.hilist_name LIKE '%手法%' OR B.hilist_name LIKE '%按摩%' OR B.hilist_name LIKE '%康复%' OR B.hilist_name LIKE '%理疗%')
      AND A.chfpdr_name != ''
    GROUP BY A.chfpdr_name, B.fee_ocur_time
    HAVING psn_count > 1
    ORDER BY psn_count DESC
    LIMIT 10
    """
    print("Executing query...")
    try:
        res = client.query(sql)
        print(f"Results ({len(res)}):")
        for row in res:
            print(f"  - {row}")
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    test_query()
