import sys
import os
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    res = client.query("SELECT * FROM default.fqz_all_yy_yd_1 LIMIT 20")
    for r in res:
        print(r)

if __name__ == '__main__':
    main()
