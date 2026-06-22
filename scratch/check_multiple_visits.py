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
    
    # 1. 查找同一个人在同一天内，在不同机构就诊的记录数
    q = """
    SELECT psn_no, count(DISTINCT fixmedins_code) as h_count, toDate(setl_time) as d
    FROM default.fqz_gz_jzsj_all_ql
    GROUP BY psn_no, d
    HAVING h_count > 1
    LIMIT 20
    """
    res = client.query(q)
    print("=== Patients with multiple hospital visits on same day ===")
    for r in res:
        print(repr(r))
        
    # 2. 针对这批患者，拉出他们具体的就诊时间、机构、城市、区划
    if res:
        target_psn = res[0]['psn_no']
        target_date = str(res[0]['d'])
        print(f"\n=== Detailed visits for patient {target_psn} on {target_date} ===")
        q_detail = f"""
        SELECT setl_time, fixmedins_code, fixmedins_name, 
               admdvs_cityname, fix_blng_admdvs, addr, insu_admdvs,
               admdvs_prvname, admdvs_city
        FROM default.fqz_gz_jzsj_all_ql
        WHERE psn_no = '{target_psn}' AND toDate(setl_time) = '{target_date}'
        ORDER BY setl_time
        """
        res_detail = client.query(q_detail)
        for rd in res_detail:
            print(repr(rd))

if __name__ == '__main__':
    main()
