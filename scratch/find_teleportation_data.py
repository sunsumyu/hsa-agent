import sys
import os
sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    
    # 1. 看看数据库里都在哪些城市/区划
    print("=== Distinct Cities ===")
    res = client.query("SELECT DISTINCT admdvs_cityname, fix_blng_admdvs_city FROM default.fqz_gz_jzsj_all_ql LIMIT 50")
    for row in res:
        print(row)
        
    # 2. 查找 2 小时内同一人有两次及以上不同定点机构的结算记录
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
        print(row)

if __name__ == '__main__':
    main()
