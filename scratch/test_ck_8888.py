import sys
import os
sys.path.append(os.getcwd())
import asyncio
from app.tools import get_clickhouse_client

def check_8888():
    try:
        client = get_clickhouse_client()
        query1 = "SELECT count(*) FROM fqz_gz_jzsj_all_ql WHERE tel LIKE '%8888%'"
        
        try:
            res1 = client.query(query1).result_rows[0][0]
            print(f"tel 包含 8888 的记录数: {res1}")
        except Exception as e:
            print(f"查询 tel 报错: {e}")
            
    except Exception as e:
        print(f"ClickHouse连接失败: {e}")

if __name__ == "__main__":
    check_8888()
