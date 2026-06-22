from app.infra.db_conn import get_clickhouse_client

client = get_clickhouse_client()
res = client.query("DESCRIBE TABLE fqz_gz_jzsj_all_ql")
for row in res.result_rows:
    col = row[0]
    if "fixmedins_code" in col:
        print(f"FOUND in fqz_gz_jzsj_all_ql: {repr(col)}")
