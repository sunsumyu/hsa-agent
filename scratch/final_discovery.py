from app.tools import _execute_audit_sql_logic

def find_the_truth():
    print("Final Discovery: Hunting for the table that actually has MONEY...")
    
    # 查找所有带 'fund' 或 'pay' 且记录数 > 0 的表
    sql = "SELECT table, name FROM system.columns WHERE (name LIKE '%fund%' OR name LIKE '%pay%') AND database = 'default'"
    try:
        cols = _execute_audit_sql_logic(sql, return_raw=True)
        unique_tables = sorted(list(set(c['table'] for c in cols)))
        print(f"Checking {len(unique_tables)} potential 'Money Tables'...")
        
        for table in unique_tables:
            # 找到这张表里所有金额列
            t_cols = [c['name'] for c in cols if c['table'] == table]
            
            # 检查是否有 > 0 的数据
            for col in t_cols:
                probe_sql = f"SELECT count() as cnt, sum({col}) as total FROM {table} WHERE {col} > 0"
                try:
                    res = _execute_audit_sql_logic(probe_sql, return_raw=True)
                    if res[0]['cnt'] > 0:
                        print(f"!!! FOUND MONEY IN {table}.{col} !!!")
                        print(f"    Rows > 0: {res[0]['cnt']} | Total: {res[0]['total']}")
                        # 再看看这张表有哪些关联键
                        key_sql = f"SELECT name FROM system.columns WHERE table = '{table}' AND name IN ('psn_no', 'mdtrt_id', 'setl_id', 'setl_no', 'certno')"
                        keys = _execute_audit_sql_logic(key_sql, return_raw=True)
                        print(f"    Possible Keys: {[k['name'] for k in keys]}")
                        break
                except:
                    pass
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    find_the_truth()
