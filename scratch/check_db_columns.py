import sys
import os
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    for table in ['fqz_all_yy_yd_1', 'fqz_admdvs', 'fqz_gz_jzsj_all_ql']:
        try:
            print(f"\n=== Columns of {table} ===")
            res = client.query(f"DESCRIBE TABLE default.{table}")
            for row in res:
                print(f"  {row['name']}: {row['type']}")
        except Exception as e:
            print(f"Failed to describe {table}: {e}")

if __name__ == '__main__':
    main()
