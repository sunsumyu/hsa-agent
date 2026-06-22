import clickhouse_connect
client = clickhouse_connect.get_client(host='localhost', port=8123, database='default')

# 检查模拟数据是否插入
res = client.query("SELECT count() FROM default.fqz_fymx_test WHERE fixmedins_name LIKE '%庙塘%' OR fixmedins_name LIKE '%哲觉%'")
print("mock data count (miaotan OR zhejue):", res.result_rows)

res2 = client.query("SELECT count() FROM default.fqz_fymx_test")
print("total fymx rows:", res2.result_rows)

# 验证批量刷单查询
FDT = "toDateTime(substring(trim(setl_time), 1, 19))"
sql = f"""
SELECT 
    toDate({FDT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FDT}), max({FDT})) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 5 AND span_seconds <= 300
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 10
"""
res3 = client.query(sql)
print("Batch billing hits:", len(res3.result_rows))
for r in res3.result_rows:
    print(" ", r)
