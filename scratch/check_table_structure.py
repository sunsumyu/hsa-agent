from app.tools import _execute_audit_sql_logic
import json

def check_structure():
    tables = ['fqz_all_yy_yd_1', 'fqz_cgzhan_tcq', 'fqz_gz_jzsj_all_ql']
    for table in tables:
        print(f"\nStructure for {table}:")
        sql = f"SELECT name, type FROM system.columns WHERE table = '{table}' AND database = 'default'"
        try:
            cols = _execute_audit_sql_logic(sql, return_raw=True)
            print([c['name'] for c in cols])
            
            # 抽样前3条
            print(f"Sample data for {table}:")
            data = _execute_audit_sql_logic(f"SELECT * FROM {table} LIMIT 3", return_raw=True)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_structure()
