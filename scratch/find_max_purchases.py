from app.tools import get_clickhouse_client
client = get_clickhouse_client()
result = client.query("SELECT max(c) FROM (SELECT count() as c FROM fqz_gz_jzsj_all_ql GROUP BY psn_no)")
print("Max purchases per person overall:", result.result_rows)

result2 = client.query("SELECT psn_no, count() as c FROM fqz_gz_jzsj_all_ql GROUP BY psn_no ORDER BY c DESC LIMIT 3")
print("Top 3 people:", result2.result_rows)
