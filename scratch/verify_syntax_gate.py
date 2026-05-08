import sys
import os
# 添加当前目录到路径
sys.path.append(os.getcwd())

from app.security import SQLGuardian, SecurityViolationError

def test_syntax_guard():
    print("\n" + "="*60)
    print(">>> [SECURITY AUDIT] SQLGuardian AST 级防线测试")
    print("="*60)

    test_cases = [
        {
            "name": "TEST 1: 语法硬伤测试 (缺少右括号)",
            "sql": "SELECT * FROM fqz_admdvs WHERE admdvs IN ('110000', '120000'",
            "expect": "PARSE FAILED"
        },
        {
            "name": "TEST 2: 危险指令拦截 (DROP TABLE)",
            "sql": "/* Bypass test */ DROP TABLE fqz_gz_jzsj_all_ql",
            "expect": "FORBIDDEN NODES"
        },
        {
            "name": "TEST 3: 隐蔽注入拦截 (UNION ALL + UPDATE)",
            "sql": "SELECT * FROM fqz_admdvs UNION ALL SELECT * FROM (UPDATE fqz_admdvs SET admdvs='999999')",
            "expect": "FORBIDDEN NODES"
        },
        {
            "name": "TEST 4: 算力爆破拦截 (巨型表全量 JOIN)",
            "sql": "SELECT a.* FROM fqz_gz_jzsj_all_ql a JOIN fqz_gz_jzsj_all_ql b ON a.psn_no = b.psn_no",
            "expect": "COMPLEXITY DENIED"
        },
        {
            "name": "TEST 5: 合法复杂查询验证 (WITH + SETTINGS)",
            "sql": "WITH tmp AS (SELECT 1) SELECT * FROM fqz_admdvs SETTINGS max_threads=1",
            "expect": "PASS"
        }
    ]

    for case in test_cases:
        print(f"\n[RUNNING] {case['name']}")
        print(f"SQL: {case['sql']}")
        try:
            validated_sql = SQLGuardian.validate_sql(case['sql'])
            print(">>> SUCCESS: PASS")
            if "SETTINGS" in validated_sql:
                print(">>> SHIELD INJECTED: YES")
        except SecurityViolationError as e:
            print(f">>> INTERCEPTED: {e}")
        except Exception as e:
            print(f">>> FAILED: CRASHED - {e}")

if __name__ == "__main__":
    test_syntax_guard()
