import os
import sys
from dotenv import load_dotenv

# 确保能加载到 app 模块
sys.path.append(os.getcwd())

load_dotenv()

from app.infra.db_conn import get_clickhouse_client

def test_connection():
    print(">>> 正在尝试连接 ClickHouse...")
    print(f"HOST: {os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}")
    print(f"PORT: {os.getenv('CLICKHOUSE_PORT', '8123')}")
    
    try:
        client = get_clickhouse_client()
        result = client.query("SELECT version()")
        print(f"✅ 连接成功! ClickHouse 版本: {result.result_rows[0][0]}")
        
        print("\n>>> 正在列出可用表:")
        tables = client.query("SHOW TABLES")
        for row in tables.result_rows:
            print(f"- {row[0]}")
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")

if __name__ == "__main__":
    test_connection()
