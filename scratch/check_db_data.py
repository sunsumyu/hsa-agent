import sys, os
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

client = get_clickhouse_client()

print("--- med_type distribution in fqz_gz_jzsj_all_ql ---")
res = client.query("SELECT med_type, count() FROM default.fqz_gz_jzsj_all_ql GROUP BY med_type")
for r in res:
    print(r)

print("\n--- row counts and time ranges ---")
res2 = client.query("SELECT count(), min(setl_time), max(setl_time) FROM default.fqz_gz_jzsj_all_ql")
for r in res2:
    print(r)

print("\n--- row counts in fqz_fymx_test ---")
try:
    res3 = client.query("SELECT count(), min(setl_time), max(setl_time) FROM default.fqz_fymx_test")
    for r in res3:
        print(r)
except Exception as e:
    print("Error querying fqz_fymx_test:", e)
