import sys, os
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def show_all():
    try:
        client = get_clickhouse_client()
        print("Successfully connected to ClickHouse!")
        
        # 1. 查询所有数据库
        dbs_res = client.query("SHOW DATABASES")
        dbs = [list(row.values())[0] if isinstance(row, dict) else row for row in dbs_res]
        print(f"\nAll Databases: {dbs}")
        
        for db in dbs:
            if db in ['INFORMATION_SCHEMA', 'information_schema', 'system']:
                continue
            print(f"\n--- Tables in Database: {db} ---")
            client.query(f"USE {db}")
            tables_res = client.query("SHOW TABLES")
            for t in tables_res:
                t_name = list(t.values())[0] if isinstance(t, dict) else t
                try:
                    count_res = client.query(f"SELECT count() FROM {t_name}")
                    count = count_res[0][list(count_res[0].keys())[0]] if isinstance(count_res[0], dict) else count_res[0]
                    print(f"  - {t_name}: {count} rows")
                except Exception as ex:
                    print(f"  - {t_name}: ERROR counting rows ({ex})")
                
    except Exception as e:
        print(f"Connection/Query error: {e}")

if __name__ == "__main__":
    show_all()
