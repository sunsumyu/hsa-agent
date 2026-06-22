from app.tools import _execute_audit_sql_logic

def deep_discover_audit_tables():
    print("Deep Discovery: Searching for high-quality audit tables...")
    
    # 1. 寻找同时包含 psn_no 和 fund_pay_sumamt 的表
    sql_find_tables = """
    SELECT table 
    FROM system.columns 
    WHERE name IN ('psn_no', 'fund_pay_sumamt') 
      AND database = 'default' 
    GROUP BY table 
    HAVING count() = 2
    """
    
    try:
        tables = _execute_audit_sql_logic(sql_find_tables, return_raw=True)
        print(f"Found {len(tables)} candidate tables.")
        
        for item in tables:
            table_name = item['table']
            # 2. 探测每张表的行数和统筹支付有效性
            sql_probe = f"SELECT count(), sum(fund_pay_sumamt) FROM {table_name} WHERE fund_pay_sumamt > 0"
            try:
                res = _execute_audit_sql_logic(sql_probe, return_raw=True)
                print(f"Table: {table_name:30} | Rows with Fund > 0: {res[0]['count()']:10} | Total Fund: {res[0]['sum(fund_pay_sumamt)']:15}")
            except Exception as e:
                print(f"Table: {table_name:30} | Error: {e}")
                
    except Exception as e:
        print(f"Discovery failed: {e}")

if __name__ == "__main__":
    deep_discover_audit_tables()
