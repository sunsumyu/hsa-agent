import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import clickhouse_connect

client = clickhouse_connect.get_client(
    host="localhost",
    port=8123,
    username="default",
    password=""
)

sql = """
SELECT psn_no, fixmedins_code, toDate(setl_time), count(*) 
FROM fqz_gz_jzsj_all_ql 
WHERE toYear(setl_time) = 2024 
GROUP BY psn_no, fixmedins_code, toDate(setl_time) 
HAVING count(*) > 1 
ORDER BY count(*) DESC
LIMIT 20
"""
res = client.query(sql).result_rows
print("Results length:", len(res))
for idx, r in enumerate(res[:10]):
    print(f"  Row {idx}: {r!r}")
