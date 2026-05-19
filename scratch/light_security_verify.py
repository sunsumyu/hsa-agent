import os
# 仅导入 Security 核心，不加载 tools.py 中的重型模型
from app.skills.security import SQLGuardian, SQLComplexityError

def light_verify():
    print("\n" + "="*50)
    print(">>> [LIGHT VERIFY] 启动轻量级安全拦截测试")
    print("="*50 + "\n")

    # --- 1. 算力代价拦截测试 (V43.0 Regex Mode) ---
    print("CASE 1: 检测大表无索引自连接拦截...")
    # 场景：未提供 psn_no 等值过滤的自连接
    high_risk_sql = """
    SELECT a.psn_no, COUNT(*) 
    FROM fqz_gz_jzsj_all_ql a 
    JOIN fqz_gz_jzsj_all_ql b ON a.start_date = b.start_date 
    GROUP BY a.psn_no
    """
    try:
        SQLGuardian.validate_sql(high_risk_sql)
        print("[FAIL] Case 1 失败：高危 SQL 意外逃脱！")
    except SQLComplexityError as e:
        print(f"[PASS] Case 1 成功：正则拦截器已物理触发 -> {e}")

    # --- 2. 算力代价放行测试 (Safe Case) ---
    print("\nCASE 2: 检测合法自连接放行...")
    # 场景：提供了 psn_no = 'xxx' 过滤逻辑
    safe_sql = """
    SELECT a.psn_no, COUNT(*) 
    FROM fqz_gz_jzsj_all_ql a 
    JOIN fqz_gz_jzsj_all_ql b ON a.psn_no = b.psn_no 
    WHERE a.psn_no = 'P12345'
    """
    try:
        SQLGuardian.validate_sql(safe_sql)
        print("[PASS] Case 2 成功：合法 SQL 允许放行。")
    except Exception as e:
        print(f"[FAIL] Case 2 失败：合法 SQL 被误拦截 -> {e}")

    # --- 3. 资源配额注入测试 ---
    print("\nCASE 3: 检测资源配额注入...")
    res_sql = SQLGuardian.validate_sql("SELECT 1")
    if "max_memory_usage=2000000000" in res_sql:
        print(f"[PASS] Case 3 成功：2GB 内存限额强制注入。")
    else:
        print("[FAIL] Case 3 失败：资源设置注入缺失。")

if __name__ == "__main__":
    light_verify()
