import os
import clickhouse_connect
from dotenv import load_dotenv

def fast_audit():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # 利用 ClickHouse 系统表秒级定位
    sql = """
    SELECT 
        database, 
        table, 
        name, 
        type 
    FROM system.columns 
    WHERE database IN ('default', 'fqz_hsa') 
      AND name IN ('psn_no', 'start_date', 'med_type', 'ipt_days', 'medfee_sumamt')
    ORDER BY database, table
    """
    
    res = client.query(sql)
    print(f"{'DB':<10} | {'Table':<30} | {'Field':<15} | {'Type':<15}")
    print("-" * 80)
    
    for r in res.result_rows:
        print(f"{r[0]:<10} | {r[1]:<30} | {r[2]:<15} | {r[3]:<15}")

if __name__ == "__main__":
    fast_audit()
