import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.db_conn import get_clickhouse_client

def run_query():
    client = get_clickhouse_client()
    
    # Value distribution
    res = client.query("SELECT medfee_sumamt, count() as cnt FROM fqz_gz_jzsj_all_ql GROUP BY medfee_sumamt ORDER BY medfee_sumamt DESC")
    print("Value distribution in fqz_gz_jzsj_all_ql:")
    for row in res:
        print(row)

if __name__ == '__main__':
    run_query()
