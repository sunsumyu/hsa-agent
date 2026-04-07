import pymysql
import json

def scan_db():
    config = {
        'host': '127.0.0.1',
        'port': 3308,
        'user': 'root',
        'password': '62901990552',
        'db': 'fylqz_platform_new',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    
    report_file = "e:/chain/fqz-hsa-manage/mysql_scan_report.txt"
    
    try:
        connection = pymysql.connect(**config)
        with connection.cursor() as cursor:
            # 1. Get List of Tables
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            table_names = [list(t.values())[0] for t in tables]
            
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(f"MySQL Database Scan Report: fylqz_platform_new\n")
                f.write(f"Total Tables Found: {len(table_names)}\n")
                f.write("="*50 + "\n\n")
                
                for table in table_names:
                    f.write(f"Table: {table}\n")
                    f.write("-" * len(f"Table: {table}") + "\n")
                    
                    # 2. Get Schema
                    try:
                        cursor.execute(f"SHOW CREATE TABLE {table}")
                        create_stmt = cursor.fetchone()
                        f.write(f"Schema Definition:\n{create_stmt['Create Table']}\n\n")
                    except Exception as e:
                        f.write(f"Error fetching schema for {table}: {e}\n")
                    
                    # 3. Sample Data
                    try:
                        cursor.execute(f"SELECT * FROM {table} LIMIT 3")
                        samples = cursor.fetchall()
                        f.write(f"Sample Data (up to 3 rows):\n")
                        if not samples:
                            f.write("[Empty Table]\n")
                        else:
                            for idx, row in enumerate(samples):
                                f.write(f"Row {idx+1}: {json.dumps(row, ensure_ascii=False, default=str)}\n")
                    except Exception as e:
                        f.write(f"Error fetching samples for {table}: {e}\n")
                    
                    f.write("\n" + "="*50 + "\n\n")
        
        print(f"Scan complete. Report saved to: {report_file}")
        
    except Exception as e:
        print(f"Critical error during scan: {e}")
    finally:
        if 'connection' in locals():
            connection.close()

if __name__ == "__main__":
    scan_db()
