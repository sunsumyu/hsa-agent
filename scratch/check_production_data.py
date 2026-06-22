import os
import clickhouse_connect
from dotenv import load_dotenv

def check_production_data():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    queries = [
        ("fqz_hsa.fqz_all_yy_yd", "SELECT count(), max(medfee_sumamt) FROM fqz_hsa.fqz_all_yy_yd"),
        ("default.fqz_all_yy_yd", "SELECT count(), max(medfee_sumamt) FROM default.fqz_all_yy_yd"),
        ("default.fqz_gz_jzsj_all_ql", "SELECT count(), max(medfee_sumamt) FROM default.fqz_gz_jzsj_all_ql")
    ]
    
    print(f"{'Table':<30} | {'Count':<10} | {'Max Amount':<15}")
    print("-" * 60)
    
    for label, sql in queries:
        try:
            res = client.query(sql)
            count, max_amt = res.first_row
            print(f"{label:<30} | {count:<10} | {max_amt:<15}")
        except Exception as e:
            print(f"{label:<30} | ERROR: {str(e)[:40]}...")

if __name__ == "__main__":
    check_production_data()
