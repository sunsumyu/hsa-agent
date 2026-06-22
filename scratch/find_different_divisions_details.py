import sys
import os
import io

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    q = """
    SELECT DISTINCT
           t1.fix_blng_admdvs AS div1, t2.fix_blng_admdvs AS div2,
           t1.admdvs_cityname AS city1, t2.admdvs_cityname AS city2
    FROM default.fqz_gz_jzsj_all_ql t1
    JOIN default.fqz_gz_jzsj_all_ql t2 
      ON t1.psn_no = t2.psn_no 
     AND t1.fixmedins_code <> t2.fixmedins_code
     AND t1.fix_blng_admdvs <> t2.fix_blng_admdvs
     AND t2.setl_time BETWEEN t1.setl_time AND t1.setl_time + INTERVAL 2 HOUR
    WHERE t1.setl_time >= '2024-01-01' AND t1.setl_time < '2025-01-01'
    LIMIT 20
    """
    res = client.query(q)
    print("=== Unique Division Pairs within 2 Hours ===")
    for r in res:
        print(repr(r))

if __name__ == '__main__':
    main()
