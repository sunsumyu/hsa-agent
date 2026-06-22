from app.tools import _execute_audit_sql_logic

def find_bridge():
    print("Searching for the 'Audit Bridge' (Tables with both psn_no and amount)...")
    
    # 查找所有带 psn_no 的表
    sql = "SELECT table, groupArray(name) as cols FROM system.columns WHERE database = 'default' GROUP BY table HAVING has(cols, 'psn_no')"
    try:
        tables = _execute_audit_sql_logic(sql, return_raw=True)
        for item in tables:
            table = item['table']
            cols = item['cols']
            
            # 检查是否有任何金额相关的列
            amount_cols = [c for c in cols if 'amt' in c.lower() or 'pay' in c.lower() or 'fee' in c.lower()]
            if amount_cols:
                # 探测数据质量
                sql_probe = f"SELECT count() as total, countIf(fund_pay_sumamt > 0) as has_fund FROM {table}" if 'fund_pay_sumamt' in cols else f"SELECT count() as total, 0 as has_fund FROM {table}"
                try:
                    res = _execute_audit_sql_logic(sql_probe, return_raw=True)
                    print(f"Table: {table:30} | Total Rows: {res[0]['total']:10} | Valid Fund Rows: {res[0]['has_fund']:10} | Amt Cols: {amount_cols[:3]}")
                except:
                    print(f"Table: {table:30} | (Probe failed)")
                    
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    find_bridge()
