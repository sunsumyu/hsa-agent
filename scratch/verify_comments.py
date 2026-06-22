import os
import clickhouse_connect
from dotenv import load_dotenv

def verify_comments():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # 抽取核心流水表的注释快照
    print("\n" + "="*60)
    print(">>> [FINAL AUDIT] ClickHouse 物理元数据对位验收报告")
    print("="*60)
    
    sql = "SELECT table, name, comment FROM system.columns WHERE database = 'default' AND comment != '' AND table IN ('fqz_gz_jzsj_all_ql', 'fqz_all_yy_yd_1', 'fqz_cgzhan_hosp') LIMIT 20"
    results = client.query(sql).result_rows
    
    print(f"{'Table':<25} | {'Column':<20} | {'Comment'}")
    print("-" * 80)
    for row in results:
        print(f"{row[0]:<25} | {row[1]:<20} | {row[2]}")
    
    client.close()

if __name__ == "__main__":
    verify_comments()
