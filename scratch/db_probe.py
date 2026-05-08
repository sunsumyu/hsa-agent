import json
from app.tools import _execute_audit_sql_logic

def probe_database_quality():
    print("===========================================================")
    print("[全库多表联合探测] 正在寻找高价值审计数据源...")
    print("===========================================================\n")
    
    # 探测清单
    probes = [
        {
            "name": "ClickHouse 明细表 (fqz_all_yy_yd_1) 统筹支付质量探测",
            "sql": "SELECT count(), sum(fund_pay_sumamt) as total_fund FROM fqz_all_yy_yd_1 WHERE fund_pay_sumamt > 0"
        },
        {
            "name": "ClickHouse 宽表 (fqz_gz_jzsj_all_ql) 字段分布探测",
            "sql": "SELECT count(), avg(medfee_sumamt), avg(fund_pay_sumamt) FROM fqz_gz_jzsj_all_ql"
        },
        {
            "name": "MySQL 机构主数据 GPS 覆盖率探测",
            "sql": "SELECT count(*) FROM fqz_all_yy_yd WHERE lnt IS NOT NULL AND lat IS NOT NULL",
            "db": "mysql"
        }
    ]
    
    for probe in probes:
        print(f">>> 执行探测: {probe['name']}")
        try:
            db_type = probe.get("db", "clickhouse")
            res = _execute_audit_sql_logic(probe["sql"], db_type=db_type, return_raw=True)
            print(f"    探测结果: {res}")
        except Exception as e:
            print(f"    ❌ 探测失败: {e}")
        print("-" * 50)

if __name__ == "__main__":
    probe_database_quality()
