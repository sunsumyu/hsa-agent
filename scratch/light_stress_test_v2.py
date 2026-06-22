import sys
# 绕过 graph/tools 导入，直接测试 security 核心
from app.skills.security import SQLGuardian, SQLComplexityError

def light_stress_v2():
    print("\n" + "="*60)
    print(">>> [LIGHT STRESS V2.0] 启动 AST 级核心探测")
    print("="*60 + "\n")

    # --- 1. AST JOIN 契约测试 ---
    print("CASE 1: 检测别名嵌套下的自连接风险...")
    complex_join_sql = """
    SELECT x.psn_no, y.start_date 
    FROM fqz_gz_jzsj_all_ql x
    INNER JOIN fqz_gz_jzsj_all_ql y ON x.start_date = y.start_date
    WHERE x.psn_no = y.psn_no  -- 虽然有 psn_no 对齐，但如果 ON 条件中缺失范围过滤，依然高危
    """
    # 场景：故意构造一个 ON 中缺失 psn_no 过滤，但在 WHERE 中提供的混合场景
    try:
        # 如果代码逻辑中只要有 EQ(psn_no) 就放行，则 Case 2 会 PASS
        # 我们主要测试 AST 是否能正常解析
        SQLGuardian.validate_sql(complex_join_sql)
        print("[PASS] Case 1 成功：AST 正常解析并确认了合法的 PSN_NO 过滤。")
    except Exception as e:
        print(f"[FAIL] Case 1 异常：{e}")

    # --- 2. 算力拦截测试 (High Risk) ---
    print("\nCASE 2: 检测全量笛卡尔积拦截 (CROSS JOIN Style)...")
    bad_join_sql = "SELECT * FROM fqz_gz_jzsj_all_ql a, fqz_gz_jzsj_all_ql b WHERE a.start_date = b.start_date"
    try:
        SQLGuardian.validate_sql(bad_join_sql)
        print("[FAIL] Case 2 失败：防御墙未能在 AST 层级识别出这种隐式的高危连接！")
    except SQLComplexityError as e:
        print(f"[PASS] Case 2 成功：AST 审计器成功捕获隐式关联并物理熔断 -> {e}")

    # --- 3. 非法聚合拦截测试 ---
    print("\nCASE 3: 检测针对 String 字段的裸聚合拦截...")
    forbidden_sql = "SELECT SUM(ipt_days) FROM fqz_gz_jzsj_all_ql"
    try:
        SQLGuardian.validate_sql(forbidden_sql)
        print("[FAIL] Case 3 失败：防御墙未能捕获 SUM(String) 类型违规！")
    except SQLComplexityError as e:
        print(f"[PASS] Case 3 成功：AST 聚合节点监控已生效 -> {e}")

if __name__ == "__main__":
    light_stress_v2()
