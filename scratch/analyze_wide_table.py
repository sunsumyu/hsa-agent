from app.tools import _execute_audit_sql_logic

def analyze():
    print("Analyzing fqz_gz_jzsj_all_ql columns...")
    sql = "SELECT name, type FROM system.columns WHERE table = 'fqz_gz_jzsj_all_ql' AND database = 'default'"
    try:
        cols = _execute_audit_sql_logic(sql, return_raw=True)
        print(f"Total columns: {len(cols)}")
        
        # 筛选看起来像金额或支付的字段
        money_keywords = ['amt', 'pay', 'fee', 'sum', 'cost', 'balc']
        money_cols = [c for c in cols if any(k in c['name'].lower() for k in money_keywords)]
        
        print("\nPotential Money Columns:")
        for mc in money_cols:
            # 探测该列是否有 > 0 的值
            probe_sql = f"SELECT count() FROM fqz_gz_jzsj_all_ql WHERE {mc['name']} > 0"
            try:
                res = _execute_audit_sql_logic(probe_sql, return_raw=True)
                count = res[0]['count()']
                print(f"Column: {mc['name']:30} | Type: {mc['type']:20} | Rows > 0: {count}")
            except:
                print(f"Column: {mc['name']:30} | Type: {mc['type']:20} | (Probe failed)")
                
    except Exception as e:
        print(f"Analysis failed: {e}")

if __name__ == "__main__":
    analyze()
