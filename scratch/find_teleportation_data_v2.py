import sys
import os
import io

# Force stdout to be utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    print("=== Distinct Cities ===")
    res = client.query("SELECT DISTINCT admdvs_cityname, fix_blng_admdvs_city FROM default.fqz_gz_jzsj_all_ql LIMIT 50")
    for row in res:
        print(repr(row))
        
    print("\n=== Multi-visit in 2 Hours ===")
    q = """
    SELECT t1.psn_no, t1.psn_name, t1.fixmedins_name AS h1, t2.fixmedins_name AS h2, 
           t1.setl_time AS t1_time, t2.setl_time AS t2_time,
           t1.admdvs_cityname AS city1, t2.admdvs_cityname AS city2,
           t1.fix_blng_admdvs AS div1, t2.fix_blng_admdvs AS div2
    FROM default.fqz_gz_jzsj_all_ql t1
    JOIN default.fqz_gz_jzsj_all_ql t2 
      ON t1.psn_no = t2.psn_no 
     AND t1.fixmedins_code <> t2.fixmedins_code
     AND t2.setl_time BETWEEN t1.setl_time AND t1.setl_time + INTERVAL 2 HOUR
    WHERE t1.setl_time >= '2024-01-01' AND t1.setl_time < '2025-01-01'
    LIMIT 20
    """
    res2 = client.query(q)
    for row in res2:
        print(repr(row))

if __name__ == '__main__':
    main()
