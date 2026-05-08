import os
import clickhouse_connect
from dotenv import load_dotenv

def storage_radar():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    print(f"--- ClickHouse 全域容量雷达扫描 ---")
    try:
        # 不指定 database，扫描全域
        client = clickhouse_connect.get_client(
            host=host, port=port, username=user,
            settings={'readonly': 1}
        )
        
        query = """
        SELECT 
            database, 
            table, 
            formatReadableSize(sum(data_compressed_bytes)) as storage_size, 
            sum(rows) as row_count,
            sum(data_compressed_bytes) as raw_bytes
        FROM system.parts 
        WHERE active
        GROUP BY database, table 
        ORDER BY raw_bytes DESC 
        LIMIT 20
        """
        res = client.query(query)
        
        print(f"{'数据库':<15} | {'表名':<40} | {'体积':<12} | {'行数':<12}")
        print("-" * 85)
        
        for row in res.result_rows:
            db, table, size, rows, _ = row
            status = "!!! PRODUCTION !!!" if "G" in size or "T" in size else ""
            print(f"{db:<15} | {table:<40} | {size:<12} | {rows:<12} {status}")
                
    except Exception as e:
        print(f"❌ 雷达扫描失败: {e}")

if __name__ == "__main__":
    storage_radar()
