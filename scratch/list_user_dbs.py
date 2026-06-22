import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def run():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    try:
        dbs = client.execute("SHOW DATABASES")
        print("Databases:")
        for db_row in dbs:
            db_name = db_row[0]
            if db_name in ('system', 'information_schema', 'INFORMATION_SCHEMA'):
                continue
            print(f"Database: {db_name}")
            try:
                tables = client.execute(f"SHOW TABLES FROM {db_name}")
                for t_row in tables:
                    t_name = t_row[0]
                    try:
                        cnt = client.execute(f"SELECT count() FROM {db_name}.{t_name}")[0][0]
                    except Exception:
                        cnt = "N/A"
                    print(f"  ├─ {t_name} ({cnt} rows)")
            except Exception as e:
                print(f"  Failed to show tables for {db_name}: {e}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    run()
