import os
import clickhouse_connect
from dotenv import load_dotenv

def inventory_check():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    db = os.getenv("CLICKHOUSE_DB", "default")
    
    print(f"--- ClickHouse 全量表清查 ---")
    try:
        # 使用 settings={'readonly': 1} 确保安全
        client = clickhouse_connect.get_client(
            host=host, port=port, username=user, database=db, 
            settings={'readonly': 1}
        )
        
        # 1. 获取所有表名
        tables_res = client.query("SHOW TABLES")
        tables = [row[0] for row in tables_res.result_rows]
        
        print(f"发现表总数: {len(tables)}")
        print(f"{'表名':<40} | {'行数':<12}")
        print("-" * 55)
        
        for table in tables:
            try:
                count_res = client.query(f"SELECT count() FROM {table}")
                count = count_res.first_row[0]
                status = "[ACTIVE]" if count > 0 else "[EMPTY]"
                print(f"{table:<40} | {count:<12} | {status}")
            except Exception as te:
                print(f"{table:<40} | ERROR: {te}")
                
    except Exception as e:
        print(f"❌ 清查失败: {e}")

if __name__ == "__main__":
    inventory_check()
