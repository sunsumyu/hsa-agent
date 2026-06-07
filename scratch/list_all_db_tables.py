import os, sys
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def list_dbs():
    client = get_clickhouse_client()
    try:
        dbs = client.query("SHOW DATABASES")
        print("Databases:")
        for db in dbs:
            print(f"  - {db.get('name', db)}")
            
        print("\nTables in each database:")
        for db_row in dbs:
            db_name = db_row.get('name', db_row)
            if isinstance(db_name, dict):
                db_name = list(db_name.values())[0]
            try:
                tables = client.query(f"SHOW TABLES FROM {db_name}")
                print(f"Database: {db_name}")
                for t in tables:
                    t_name = t.get('name', t)
                    if isinstance(t_name, dict):
                        t_name = list(t_name.values())[0]
                    # Get row count
                    try:
                        count_res = client.query(f"SELECT count() as c FROM {db_name}.{t_name}")
                        cnt = count_res[0]['c']
                    except Exception:
                        cnt = "N/A"
                    print(f"  ├─ {t_name} ({cnt} rows)")
            except Exception as e:
                print(f"  Failed for {db_name}: {e}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    list_dbs()
