import os
import clickhouse_connect
from dotenv import load_dotenv

def final_check():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # 构建一个物理上非法的 SQL
    illegal_sql = "SELECT SUM(ipt_days) FROM fqz_gz_jzsj_all_ql"
    # 模拟 agent_graph 中的封装逻辑
    dry_run_sql = f"SELECT * FROM ({illegal_sql}) LIMIT 0"
    
    print(f"执行物理核验 SQL: {dry_run_sql}")
    try:
        client.query(dry_run_sql)
        print("[FAIL] Case Failed: ClickHouse should reject this!")
    except Exception as e:
        print(f"[PASS] Case Passed: ClickHouse rejected illegal type as expected -> {e}")

if __name__ == "__main__":
    final_check()
