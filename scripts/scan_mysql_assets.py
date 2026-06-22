import mysql.connector
import json

def scan_mysql():
    config = {
        'user': 'root',
        'password': '62901990552',
        'host': '127.0.0.1',
        'port': 3308,
        'database': 'fylqz_platform_new',
        'charset': 'utf8mb4'
    }
    
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # 1. 获取所有表
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"TOTAL_TABLES_FOUND:{len(tables)}")
        
        audit_assets = []
        
        for table in tables:
            print(f"\n--- TABLE_SCAN_START:{table} ---")
            
            # 2. 获取结构
            cursor.execute(f"DESC {table}")
            columns = cursor.fetchall()
            print("[STRUCTURE]")
            for col in columns:
                print(f"{col[0]} | {col[1]} | {col[2]} | {col[3]}")
                
            # 3. 采样数据
            try:
                cursor.execute(f"SELECT * FROM {table} LIMIT 2")
                rows = cursor.fetchall()
                print("[SAMPLE_DATA]")
                for row in rows:
                    print(row)
            except Exception as e:
                print(f"DATA_ERROR:{str(e)}")
                
            print(f"--- TABLE_SCAN_END:{table} ---")
            
        conn.close()
    except Exception as e:
        print(f"CRITICAL_ERROR:{str(e)}")

if __name__ == "__main__":
    scan_mysql()
