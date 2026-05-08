import os
from app.security import SQLGuardian, SecurityViolationError, SQLComplexityError
from app.tools import execute_audit_sql
from loguru import logger

def verify_enterprise_guards():
    print("\n" + "="*50)
    print(">>> [企业级加固验证] 启动防线压力测试")
    print("="*50 + "\n")

    # --- 1. 算力代价拦截测试 (OOM Guard) ---
    print("CASE 1: 检测大表无索引自连接拦截...")
    high_risk_sql = """
    SELECT a.psn_no, COUNT(*) 
    FROM fqz_gz_jzsj_all_ql a 
    JOIN fqz_gz_jzsj_all_ql b ON a.start_date = b.start_date 
    GROUP BY a.psn_no
    """
    try:
        # 故意不加 psn_no 过滤
        SQLGuardian.validate_sql(high_risk_sql)
        print("[FAIL] Case 1 失败：SQL 竟然绕过了算力拦截！")
    except SQLComplexityError as e:
        print(f"[PASS] Case 1 成功：检测到算力拦截 -> {e}")

    # --- 2. 资源配额注入测试 (Quota Guard) ---
    print("\nCASE 2: 检测 ClickHouse SETTINGS 强制注入...")
    test_sql = "SELECT 1"
    secured_sql = SQLGuardian.validate_sql(test_sql)
    if "SETTINGS" in secured_sql and "max_memory_usage" in secured_sql:
        print(f"[PASS] Case 2 成功：已物理注入资源限额 -> \n{secured_sql}")
    else:
        print("[FAIL] Case 2 失败：SQL 未被注入限额设置。")

    # --- 3. 物理类型预检测试 (Dry-Run Guard) ---
    print("\nCASE 3: 检测物理类型 LIMIT 0 预检... [SKIP for Debug]")
    # illegal_type_sql = "SELECT SUM(ipt_days) FROM fqz_gz_jzsj_all_ql"
    # try:
    #     execute_audit_sql(f"SELECT * FROM ({illegal_type_sql}) LIMIT 0")
    # except Exception as e:
    #     print(f"[PASS] Case 3 成功：物理预检捕获到类型不匹配错误 -> {e}")

if __name__ == "__main__":
    verify_enterprise_guards()
